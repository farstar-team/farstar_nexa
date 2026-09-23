import hashlib
import json
import os
import shutil
import socket
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from nexa_ops.protocol import BACKUP_NAME, atomic_json, validate_metadata

import runtime as rt


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup(*, restart=True) -> str:
    rt.disk_space()
    folder = rt.DATA / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    name = "nexa-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".tar.gz"
    rt.progress("backup")
    rt.compose("stop", "api", "worker")
    try:
        with tempfile.TemporaryDirectory(dir=folder) as staging:
            temp = Path(staging)
            dump = temp / "database.dump"
            # Stream directly to disk; production databases need not fit in RAM.
            import subprocess

            env = dict(os.environ, NEXA_ENV_FILE=str(rt.CONFIG), NEXA_RELEASE=rt.version())
            args = [
                "docker",
                "compose",
                "-p",
                "farstarnexa",
                "--env-file",
                str(rt.CONFIG),
                "-f",
                str(rt.release() / "docker-compose.yml"),
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                "nexa",
                "-d",
                "nexa",
                "-Fc",
                "--no-owner",
                "--no-acl",
            ]
            with dump.open("wb") as stream:
                result = subprocess.run(args, env=env, stdout=stream, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError("Database dump failed")
            schema = (
                rt.compose(
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "nexa",
                    "-d",
                    "nexa",
                    "-Atc",
                    "SELECT version_num FROM alembic_version",
                )
                .decode()
                .strip()
            )
            shutil.copy2(rt.CONFIG, temp / "nexa.env")
            shutil.copy2(rt.DATA / "proxy/Caddyfile", temp / "Caddyfile")
            metadata = {
                "format": 1,
                "product": "farstar-nexa",
                "version": rt.version(),
                "schema": schema,
                "created_at": datetime.now(UTC).isoformat(),
                "hostname": socket.gethostname(),
                "sha256": {p.name: checksum(p) for p in temp.iterdir()},
            }
            validate_metadata(metadata, rt.version())
            atomic_json(temp / "metadata.json", metadata)
            archive = folder / (name + ".partial")
            with tarfile.open(archive, "w:gz") as tar:
                for path in temp.iterdir():
                    tar.add(path, arcname=path.name, recursive=False)
            validate_archive(archive, rt.version())
            archive.chmod(0o640)
            if hasattr(os, "chown"):
                os.chown(archive, 0, 10001)
            archive.replace(folder / name)
            atomic_json(
                folder / (name + ".json"),
                {
                    "version": rt.version(),
                    "created_at": metadata["created_at"],
                    "status": "validated",
                    "schema": schema,
                },
            )
            (folder / (name + ".json")).chmod(0o644)
    finally:
        if restart:
            rt.compose("up", "-d", "api", "worker")
    return name


def validate_archive(path: Path, installed_version: str) -> dict:
    with tarfile.open(path, "r:gz") as tar:
        members = tar.getmembers()
        expected = {"metadata.json", "database.dump", "nexa.env", "Caddyfile"}
        if len(members) != 4 or {m.name for m in members} != expected or any(not m.isfile() for m in members):
            raise ValueError("Unsafe or incomplete backup archive")
        sizes = {m.name: m.size for m in members}
        if sizes["metadata.json"] > 16384 or sizes["nexa.env"] > 65536 or sizes["Caddyfile"] > 65536:
            raise ValueError("Invalid backup component size")
        metadata = json.load(tar.extractfile("metadata.json"))
        validate_metadata(metadata, installed_version)
        for name, expected_hash in metadata["sha256"].items():
            if hashlib.file_digest(tar.extractfile(name), "sha256").hexdigest() != expected_hash:
                raise ValueError("Backup checksum mismatch")
        with tar.extractfile("database.dump") as dump:
            if dump.read(5) != b"PGDMP":
                raise ValueError("Not a PostgreSQL custom-format dump")
        return metadata


def restore(name: str):
    if not BACKUP_NAME.fullmatch(name):
        raise ValueError("Invalid backup name")
    path = rt.DATA / "backups" / name
    if path.is_symlink():
        raise ValueError("Symlink backups are not supported")
    rt.progress("validating")
    validate_archive(path, rt.version())
    rt.disk_space()
    safety = backup(restart=False)
    print("Safety backup: " + safety, flush=True)
    # Leave writers stopped after any failure, so an operator can investigate without additional writes.
    with tempfile.TemporaryDirectory(dir=rt.DATA) as staging:
        temp = Path(staging)
        with tarfile.open(path, "r:gz") as tar:
            for member in tar.getmembers():
                with (
                    tar.extractfile(member) as src,
                    (temp / member.name).open("wb") as dst,
                ):
                    shutil.copyfileobj(src, dst)
        # Validate the dump catalog before changing the live database.
        rt.compose("cp", str(temp / "database.dump"), "postgres:/tmp/nexa-restore.dump")
        rt.compose("exec", "-T", "postgres", "pg_restore", "--list", "/tmp/nexa-restore.dump")
        rt.progress("restoring")
        rt.compose(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            "nexa",
            "-d",
            "nexa",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            "--single-transaction",
            "/tmp/nexa-restore.dump",
        )
        restored = {}
        for line in (temp / "nexa.env").read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                restored[key] = value
        # Keep this server's paths and DB password; restore application encryption and integration configuration.
        preserve = {
            key: value
            for key, value in restored.items()
            if key
            in {
                "SECRET_KEY",
                "ENCRYPTION_KEYS",
                "META_APP_ID",
                "META_APP_SECRET",
                "META_VERIFY_TOKEN",
                "META_API_VERSION",
                "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_BOT_USERNAME",
                "TELEGRAM_WEBHOOK_SECRET",
                "REGISTRATION_ENABLED",
                "BASE_URL",
                "CADDY_SITE",
                "ENVIRONMENT",
                "COOKIE_SECURE",
                "MOCK_MODE",
            }
        }
        rt.save_environment(preserve)
        shutil.copyfile(temp / "Caddyfile", rt.DATA / "proxy/Caddyfile")
    rt.progress("migrating")
    rt.compose("run", "--rm", "migrate")
    rt.compose("exec", "-T", "postgres", "rm", "-f", "/tmp/nexa-restore.dump")
    rt.compose("up", "-d", "--force-recreate", "api", "worker", "proxy")
    rt.progress("health")
    rt.health()
    return {"safety_backup": safety}
