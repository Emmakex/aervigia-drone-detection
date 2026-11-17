"""Read-only reporting for bounded, SIMULATION-ONLY incident history.

No precise positions, real sensor feeds or personal tokens are included.
All outputs are explicit about their non-operational, recent-window scope.
"""

import csv
from datetime import datetime, timezone
from io import StringIO


COLUMNS = (
    "reference", "status", "type", "track_id", "zone_id", "detected_at",
    "reviewed_at", "reviewed_by", "closed_at", "closed_by", "simulation",
)
STATUSES = ("pending", "acknowledged", "closed")
NOTICE = "SYNTHETIC DEMO ONLY — not evidence of real airspace events"


def incident_report(item: dict) -> dict:
    """Whitelist report fields; never export raw sensor observations/positions."""
    status = item.get("status", "acknowledged" if item.get("acknowledged") else "pending")
    return {
        "reference": item["reference"],
        "status": status,
        "type": item["type"],
        "track_id": item["track_id"],
        "zone_id": item["zone_id"],
        "detected_at": item["at"],
        "reviewed_at": item.get("acknowledged_at"),
        "reviewed_by": item.get("acknowledged_by"),
        "closed_at": item.get("closed_at"),
        "closed_by": item.get("closed_by"),
        "simulation": True,
    }


def collection_report(items: list[dict], status: str = "all") -> dict:
    """One consistent snapshot of up to 80 latest visible demo incidents."""
    if status not in (*STATUSES, "open", "all"):
        raise ValueError("Unsupported incident status")
    reports = [incident_report(item) for item in items[:80]]
    totals = {name: sum(r["status"] == name for r in reports) for name in STATUSES}
    if status == "open":
        chosen = [r for r in reports if r["status"] != "closed"]
    elif status == "all":
        chosen = reports
    else:
        chosen = [r for r in reports if r["status"] == status]
    return {
        "schema_version": "0.4",
        "simulation": True,
        "notice": NOTICE,
        "scope": "current-reset-only, latest 80 incidents; retention applies",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filter": status,
        "totals": {"all": len(reports), **totals},
        "exported_count": len(chosen),
        "incidents": chosen,
    }


def csv_cell(value: object) -> str:
    """Prevent spreadsheet formula execution on untrusted text values."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def csv_report(report: dict) -> str:
    """UTF-8 BOM makes Excel display accented headers and data correctly."""
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for item in report["incidents"]:
        writer.writerow([csv_cell(item.get(column)) for column in COLUMNS])
    return "\ufeff" + stream.getvalue()
