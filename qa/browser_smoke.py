"""Real Chromium smoke test for AERVIGIA's LOCAL synthetic demo.

Run in PR-only CI. No external sensors, deployments, addresses or credentials.
Screenshots contain synthetic data and password fields rendered masked.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aervigia.auth import UserRegistry  # noqa: E402
SHOTS = ROOT / "qa" / "artifacts"
SHOTS.mkdir(parents=True, exist_ok=True)


def http_json(url, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, headers=headers, data=body, method="POST" if body else "GET")
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def assert_no_overflow(page, label):
    measurement = page.evaluate("""() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      header: document.querySelector('.header').getBoundingClientRect().right
    })""")
    assert measurement["document"] <= measurement["viewport"] + 1, (
        f"Horizontal overflow at {label}: {measurement}"
    )
    assert measurement["header"] <= measurement["viewport"] + 1, (
        f"Header overflow at {label}: {measurement}"
    )


def run_test():
    with tempfile.TemporaryDirectory(prefix="aervigia-browser-") as temp:
        folder = Path(temp)
        registry = UserRegistry(str(folder / "users.json"))
        viewer = registry.add("qaViewer", "viewer")
        operator = registry.add("qaOperator", "operator")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ)
        env.update({
            "AERVIGIA_USERS_FILE": str(folder / "users.json"),
            "AERVIGIA_DB_PATH": str(folder / "incidents.sqlite3"),
            "AERVIGIA_RETENTION_DAYS": "7",
        })
        # The test API lives only on localhost and dies with this script.
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "aervigia.app:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            for _ in range(60):
                if server.poll() is not None:
                    raise AssertionError("Development server stopped unexpectedly")
                try:
                    if http_json(base + "/healthz")["status"] == "ok":
                        break
                except (URLError, ConnectionError, TimeoutError):
                    time.sleep(0.25)
            else:
                raise AssertionError("Development server did not become ready")

            # Inject one fictional observation to exercise alert acknowledgment.
            http_json(base + "/api/observations", {
                "schema_version": "0.1",
                "observation_id": "qa-browser-event-001",
                "source_id": "qa-fixture",
                "source_type": "simulator",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "position": {"latitude": 0.0, "longitude": 0.0},
                "position_uncertainty_m": 5,
                "classification": "unknown",
                "simulation": True,
            }, token=operator)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1440, "height": 900},
                                        device_scale_factor=1)
                page.goto(base, wait_until="domcontentloaded")
                page.keyboard.press("Tab")
                assert page.evaluate(
                    "() => document.activeElement?.classList?.contains('skip-link')"
                ), "Skip-to-content must be first keyboard focus target"
                page.keyboard.press("Enter")
                page.locator("#named-auth").wait_for(state="visible")
                assert page.locator("#legacy-auth").is_hidden()
                page.locator("#connection").get_attribute("id")
                # Unauthenticated users cannot retain any operational data.
                page.wait_for_function("document.querySelector('#trackcount').textContent === '—'")
                assert page.locator("#alerts button").count() == 0
                page.locator("#usertoken").fill(viewer)
                page.locator("#usertoken").dispatch_event("change")
                page.wait_for_function("document.querySelector('#trackcount').textContent !== '—'")
                assert page.locator("#authidentity").inner_text().find("qaViewer") >= 0
                assert page.locator("#alerts button").count() == 0, "Viewer must not acknowledge"

                for width, height in [(1440, 900), (768, 1024), (390, 844), (320, 750)]:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(150)
                    assert_no_overflow(page, f"{width}x{height}")
                    if width in (1440, 390):
                        page.screenshot(path=str(SHOTS / f"aervigia-{width}.png"), full_page=True)
                page.set_viewport_size({"width": 1440, "height": 900})

                page.locator("#usertoken").fill(operator)
                page.locator("#usertoken").dispatch_event("change")
                page.wait_for_function("document.querySelector('#authidentity').textContent.includes('qaOperator')")
                pending = page.locator("#alerts button.ack").first
                pending.wait_for(state="visible")
                focus_id = pending.get_attribute("data-alert-id")
                pending.focus()
                # Trigger an automatic redraw while the keyboard is on the action.
                page.wait_for_timeout(1950)
                assert page.evaluate(
                    "() => document.activeElement?.dataset?.alertId"
                ) == focus_id, "Live refresh must preserve keyboard focus"
                page.locator(f'button[data-alert-id="{focus_id}"]').click()
                page.locator("#operation-feedback").get_by_text("marcada como revisada").wait_for()
                page.wait_for_function(
                    "document.querySelector('#alerts').textContent.includes('REVISADA')"
                )
                assert "qaOperator" in page.locator("#audit").inner_text()
                page.screenshot(path=str(SHOTS / "aervigia-reviewed.png"), full_page=True)

                # A local logout clears operational state and the personal token.
                page.locator("#logout").click()
                assert page.locator("#usertoken").input_value() == ""
                assert page.locator("#trackcount").inner_text() == "—"
                assert page.locator("#alerts button").count() == 0
                page.locator("#usertoken").fill(operator)
                page.locator("#usertoken").dispatch_event("change")
                page.wait_for_function("document.querySelector('#trackcount').textContent !== '—'")

                # A revoked operator loses visibility; old tracks must disappear.
                registry.revoke("qaOperator")
                page.wait_for_function(
                    "document.querySelector('#trackcount').textContent === '—'",
                    timeout=7000
                )
                assert page.locator("#alerts button").count() == 0
                assert "qa-fixture" not in page.locator("#trackrows").inner_text()
                assert "qaOperator" not in page.locator("#audit").inner_text()
                page.screenshot(path=str(SHOTS / "aervigia-revoked.png"), full_page=True)
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=6)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)


if __name__ == "__main__":
    run_test()
    print("PASS: browser desktop/mobile layout, viewer/operator alert flow and access revocation")
