"""Named local demo accounts, role checks and revocable opaque bearer tokens.

No password or shared global operator key is required in named-account mode.
Store only SHA-256 hashes of securely generated high-entropy tokens. The
registry is checked for each request so an account revoke takes effect
without restarting the application. Not an Internet-facing identity provider.
"""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile


ROLES = {"viewer", "operator", "admin"}
USER_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{2,31}$")
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str


class UserRegistry:
    def __init__(self, path: str):
        self.path = Path(path).expanduser()

    def read_users(self) -> list[dict]:
        # A missing/corrupt file is NOT a reason to fall back to legacy credentials.
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("Unsupported user registry schema")
        users = raw.get("users")
        if not isinstance(users, list) or len(users) > 1000:
            raise ValueError("Invalid users list")
        identities, hashes = set(), set()
        for item in users:
            if not isinstance(item, dict) or set(item) != {"id", "role", "token_hash"}:
                raise ValueError("Invalid user record")
            user, role, digest = item["id"], item["role"], item["token_hash"]
            if (not isinstance(user, str) or not USER_PATTERN.fullmatch(user)
                    or not isinstance(role, str) or role not in ROLES or not isinstance(digest, str)
                    or not DIGEST_PATTERN.fullmatch(digest)):
                raise ValueError("Invalid user credentials or role")
            if user in identities or digest in hashes:
                raise ValueError("Duplicate user or token hash")
            identities.add(user)
            hashes.add(digest)
        return users

    def authenticate(self, authorization: str | None) -> Identity:
        if not authorization or not authorization.startswith("Bearer "):
            raise PermissionError("Personal bearer token required")
        token = authorization.removeprefix("Bearer ").strip()
        if len(token) < 32 or len(token) > 256:
            raise PermissionError("Invalid bearer token")
        digest = sha256(token.encode("utf-8")).hexdigest()
        for item in self.read_users():
            if hmac.compare_digest(digest, item["token_hash"]):
                return Identity(item["id"], item["role"])
        raise PermissionError("Invalid bearer token")

    def add(self, user_id: str, role: str) -> str:
        if not USER_PATTERN.fullmatch(user_id):
            raise ValueError("User IDs must be 3-32 alphanumeric, _ or -, starting with a letter")
        if role not in ROLES:
            raise ValueError("Unknown role")
        users = self.read_users() if self.path.exists() else []
        if any(item["id"] == user_id for item in users):
            raise ValueError("User already exists; revoke before provisioning a replacement")
        token = secrets.token_urlsafe(40)
        users.append({
            "id": user_id, "role": role,
            "token_hash": sha256(token.encode("utf-8")).hexdigest(),
        })
        self._write(users)
        return token

    def revoke(self, user_id: str) -> bool:
        users = self.read_users()
        updated = [item for item in users if item["id"] != user_id]
        if len(updated) == len(users):
            return False
        self._write(updated)
        return True

    def _write(self, users: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement; never write a partially valid access registry.
        fd, name = tempfile.mkstemp(prefix=".users-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"schema_version": 1, "users": users}, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description="Manage AERVIGIA demo operator credentials")
    parser.add_argument("--file", required=True, help="Private JSON registry path")
    command = parser.add_subparsers(dest="command", required=True)
    add = command.add_parser("add")
    add.add_argument("--user", required=True)
    add.add_argument("--role", required=True, choices=sorted(ROLES))
    revoke = command.add_parser("revoke")
    revoke.add_argument("--user", required=True)
    command.add_parser("list")
    args = parser.parse_args()
    registry = UserRegistry(args.file)
    if args.command == "add":
        print(f"Personal token for {args.user} (save securely; shown only once):")
        print(registry.add(args.user, args.role))
    elif args.command == "revoke":
        print("Revoked" if registry.revoke(args.user) else "No matching user")
    else:
        for user in registry.read_users():
            print(user["id"], user["role"])


if __name__ == "__main__":
    main()
