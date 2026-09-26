import hashlib
import hmac
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

OPERATIONS = {"backup", "restore", "delete-backup", "domain", "ssl", "update", "check-update", "diagnostics"}
BACKUP_NAME = re.compile(r"^nexa-[0-9]{8}T[0-9]{6}-[a-f0-9]{8}\.tar\.gz$")
RELEASE = re.compile(r"^v\d+\.\d+\.\d+$")
DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
CURRENT_SCHEMA = "0003"


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sign(value: dict, secret: str) -> str:
    return hmac.new(secret.encode(), canonical(value), hashlib.sha256).hexdigest()


def validate_operation(action: str, argument: str, confirmed: bool):
    if action not in OPERATIONS:
        raise ValueError("unsupported_operation")
    if action in {"restore", "delete-backup"} and not BACKUP_NAME.fullmatch(argument):
        raise ValueError("invalid_backup_name")
    if action == "domain" and argument != "remove" and not DOMAIN.fullmatch(argument):
        raise ValueError("invalid_domain")
    if action == "update" and not RELEASE.fullmatch(argument):
        raise ValueError("release_tag_required")
    if action in {"backup", "ssl", "check-update", "diagnostics"} and argument:
        raise ValueError("unexpected_argument")
    if action in {"restore", "delete-backup", "domain", "update"} and not confirmed:
        raise ValueError("confirmation_required")


def validate_metadata(data: dict, installed_version: str):
    if data.get("format") != 1 or data.get("product") != "farstar-nexa":
        raise ValueError("unsupported_backup_format")
    if not re.fullmatch(r"\d+\.\d+\.\d+", data.get("version", "")):
        raise ValueError("invalid_backup_version")
    # Restore only this release's exact application schema. Cross-version recovery is explicit operator work.
    if data["version"] != installed_version or data.get("schema") != CURRENT_SCHEMA:
        raise ValueError("incompatible_backup")
    datetime.fromisoformat(data["created_at"])
    if not data.get("hostname") or set(data.get("sha256", {})) != {"database.dump", "nexa.env", "Caddyfile"}:
        raise ValueError("incomplete_backup")
    if any(not re.fullmatch(r"[a-f0-9]{64}", v) for v in data["sha256"].values()):
        raise ValueError("invalid_checksum")


def atomic_json(path: Path, data: dict):
    # The spool is writable by the web process. Never follow pre-created temporary symlinks as root.
    fd, name = tempfile.mkstemp(prefix=".nexa-", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(data))
            stream.flush()
            os.fsync(stream.fileno())
            if hasattr(os, "fchown") and os.geteuid() == 0:
                os.fchown(stream.fileno(), 10001, 10001)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
