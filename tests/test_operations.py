import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest
from conftest import PASSWORD
from nexa.config import Settings
from nexa.db import engine
from sqlalchemy import inspect, text

from nexa_ops.protocol import canonical, sign, validate_metadata, validate_operation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from backups import validate_archive  # noqa: E402


def metadata():
    return {
        "format": 1,
        "product": "farstar-nexa",
        "version": "0.1.0",
        "schema": "0001",
        "created_at": "2026-09-23T00:00:00+00:00",
        "hostname": "test",
        "sha256": {name: "a" * 64 for name in ["database.dump", "nexa.env", "Caddyfile"]},
    }


def test_metadata_rejects_incompatible_backups():
    valid = metadata()
    validate_metadata(valid, "0.1.0")
    for field, value in [
        ("format", 2),
        ("product", "other"),
        ("version", "0.2.0"),
        ("schema", "0002"),
        ("sha256", {}),
    ]:
        data = {**valid, field: value}
        with pytest.raises(ValueError):
            validate_metadata(data, "0.1.0")


@pytest.mark.parametrize(
    "action,argument,confirmed",
    [
        ("shell", "echo hi", True),
        ("restore", "../../private", True),
        ("restore", "nexa-20260923T000000-abcdef12.tar.gz", False),
        ("domain", "example.com;whoami", True),
        ("domain", "http://example.com", True),
        ("update", "main", True),
        ("update", "v0.2.0", False),
        ("ssl", "--config evil", True),
    ],
)
def test_operation_allowlist(action, argument, confirmed):
    with pytest.raises(ValueError):
        validate_operation(action, argument, confirmed)


def test_operation_signature_detects_changes():
    data = {"action": "backup", "argument": ""}
    assert sign(data, "private-key") != sign({**data, "action": "restore"}, "private-key")
    assert canonical(data) == canonical(dict(reversed(list(data.items()))))


def make_archive(path, malicious=False, corrupt=False):
    files = {"database.dump": b"PGDMP-test", "nexa.env": b"ENCRYPTION_KEYS=secret", "Caddyfile": b":80 {}"}
    meta = metadata()
    meta["sha256"] = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    if corrupt:
        files["database.dump"] = b"PGDMP-corrupted"
    files["metadata.json"] = json.dumps(meta).encode()
    if malicious:
        files["../escape"] = b"bad"
    with tarfile.open(path, "w:gz") as archive:
        for name, value in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))


def test_archive_validation(tmp_path):
    archive = tmp_path / "valid.tar.gz"
    make_archive(archive)
    assert validate_archive(archive, "0.1.0")["format"] == 1
    make_archive(archive, malicious=True)
    with pytest.raises(ValueError):
        validate_archive(archive, "0.1.0")
    make_archive(archive, corrupt=True)
    with pytest.raises(ValueError):
        validate_archive(archive, "0.1.0")


def test_migration_has_constraints_and_history():
    inspector = inspect(engine)
    assert {"users", "workspaces", "accounts", "jobs", "executions"} <= set(inspector.get_table_names())
    assert any(item["column_names"] == ["key"] for item in inspector.get_unique_constraints("jobs"))
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0002"
    assert {"products", "instagram_media", "leads", "workspace_rates", "action_executions"} <= set(
        inspector.get_table_names()
    )


def test_operations_offline_and_reauthentication(owner):
    assert (
        owner.post("/api/admin/operations", json={"action": "backup", "password": "incorrect"}).status_code
        == 403
    )
    assert (
        owner.post("/api/admin/operations", json={"action": "backup", "password": PASSWORD}).status_code
        == 503
    )


def test_production_rejects_mock_and_insecure_cookies():
    with pytest.raises(ValueError):
        Settings(environment="production", mock_mode=True)
