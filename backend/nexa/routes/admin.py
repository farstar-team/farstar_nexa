import json
import secrets
import time
import uuid
from typing import Literal

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from nexa.config import settings, version
from nexa.db import get_db
from nexa.integration_config import FIELDS, integration_settings
from nexa.models import Account, Audit, Execution, Job, Message, User
from nexa.models import Session as LoginSession
from nexa.routes.auth import user_dict
from nexa.routes.workspace import serialize
from nexa.security import audit, encrypt, require, verify_password
from nexa_ops.protocol import BACKUP_NAME, atomic_json, sign, validate_operation

router = APIRouter(prefix="/api/admin", tags=["admin"])


class IntegrationInput(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    values: dict[str, str]


@router.get("/integrations")
def integration_config(user: User = Depends(require("system.manage"))):
    config = integration_settings()
    return {key: bool(getattr(config, key)) for key in sorted(FIELDS)}


@router.put("/integrations")
def save_integrations(
    data: IntegrationInput, user: User = Depends(require("system.manage")), db: Session = Depends(get_db)
):
    import re

    from nexa.models import SystemSetting
    from nexa.security import rate_limit

    rate_limit("integration-config:" + user.id, 10, 600)
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(403, "invalid_credentials")
    if not set(data.values) <= FIELDS or any(len(value) > 1024 for value in data.values.values()):
        raise HTTPException(422, "validation_error")
    for key, value in data.values.items():
        if not value:
            continue
        if key == "telegram_webhook_secret" and not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value):
            raise HTTPException(422, "validation_error")
        if key == "telegram_bot_username" and not re.fullmatch(r"[A-Za-z0-9_]{5,32}", value):
            raise HTTPException(422, "validation_error")
        if "\n" in value or "\r" in value:
            raise HTTPException(422, "validation_error")
        row = db.get(SystemSetting, key)
        if row:
            row.value = encrypt(value)
        else:
            db.add(SystemSetting(key=key, value=encrypt(value)))
    audit(db, user.id, "integrations.configured", fields=sorted(data.values))
    db.commit()
    return {"ok": True}


@router.post("/telegram-webhook")
def configure_telegram(
    data: IntegrationInput, user: User = Depends(require("system.manage")), db: Session = Depends(get_db)
):
    from nexa.security import rate_limit
    from nexa.telegram import configure_webhook

    rate_limit("telegram-config:" + user.id, 5, 600)
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(403, "invalid_credentials")
    try:
        configure_webhook()
    except (ValueError, RuntimeError):
        raise HTTPException(400, "telegram_configuration_failed") from None
    audit(db, user.id, "telegram.webhook_configured")
    db.commit()
    return {"ok": True}


@router.get("/users")
def users(
    q: str = Query("", max_length=100),
    role: str = "",
    offset: int = Query(0, ge=0),
    user: User = Depends(require("users.read")),
    db: Session = Depends(get_db),
):
    query = select(User).where(User.username.contains(q.lower(), autoescape=True))
    if role:
        query = query.where(User.role == role)
    return [
        user_dict(row) for row in db.scalars(query.order_by(User.created_at.desc()).offset(offset).limit(100))
    ]


class UserUpdate(BaseModel):
    role: Literal["USER", "ADMIN", "SUPER_ADMIN"]
    active: bool


@router.patch("/users/{identity}")
def update_user(
    identity: str,
    data: UserUpdate,
    user: User = Depends(require("system.manage")),
    db: Session = Depends(get_db),
):
    row = db.scalar(select(User).where(User.id == identity).with_for_update())
    if not row:
        raise HTTPException(404, "not_found")
    if row.id == user.id:
        raise HTTPException(400, "cannot_modify_self")
    # No administrator can demote or disable a peer owner via the web API.
    if row.role == "SUPER_ADMIN":
        raise HTTPException(400, "owner_requires_cli")
    row.role, row.active = data.role, data.active
    db.execute(delete(LoginSession).where(LoginSession.user_id == row.id))
    audit(db, user.id, "user.updated", row.id, role=data.role, active=data.active)
    db.commit()
    return user_dict(row)


@router.get("/status")
def status(user: User = Depends(require("system.manage")), db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    redis_ok, worker_ok = False, False
    try:
        with Redis.from_url(settings().redis_url, socket_timeout=2) as client:
            redis_ok = client.ping()
            worker_ok = bool(client.get("nexa:worker:heartbeat"))
    except Exception:
        pass
    counts = {
        name: db.scalar(select(func.count()).select_from(model))
        for name, model in {
            "users": User,
            "accounts": Account,
            "messages": Message,
            "executions": Execution,
        }.items()
    }
    counts["active_users"] = db.scalar(select(func.count()).select_from(User).where(User.active.is_(True)))
    jobs = {
        state: db.scalar(select(func.count()).select_from(Job).where(Job.status == state))
        for state in ["pending", "failed", "unknown"]
    }
    host = settings().operations_dir / "host-status.json"
    host_status = None
    if host.is_file() and time.time() - host.stat().st_mtime < 120:
        host_status = json.loads(host.read_text())
    return {
        "version": version(),
        "counts": counts,
        "database": True,
        "redis": redis_ok,
        "worker": worker_ok,
        "jobs": jobs,
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "metric_scope": "container",
        "host": host_status,
        "base_url": settings().base_url,
        "mock_mode": settings().mock_mode,
        "meta_configured": bool(integration_settings().meta_app_id),
        "telegram_configured": bool(integration_settings().telegram_bot_token),
    }


@router.get("/audit")
def audit_log(user: User = Depends(require("system.manage")), db: Session = Depends(get_db)):
    return [
        serialize(row, "id user_id action target detail created_at")
        for row in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200))
    ]


class OperationInput(BaseModel):
    action: str = Field(max_length=32)
    argument: str = Field(default="", max_length=254)
    confirmed: bool = False
    password: str = Field(min_length=1, max_length=256)


@router.post("/operations", status_code=202)
def operation(
    data: OperationInput, user: User = Depends(require("system.manage")), db: Session = Depends(get_db)
):
    from nexa.security import rate_limit

    rate_limit("admin-operation:" + user.id, 10, 600)
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(403, "invalid_credentials")
    try:
        validate_operation(data.action, data.argument, data.confirmed)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    directory = settings().operations_dir
    heartbeat = directory / "host-status.json"
    if not heartbeat.exists() or time.time() - heartbeat.stat().st_mtime > 120:
        raise HTTPException(503, "operations_agent_offline")
    identity = str(uuid.uuid4())
    payload = {
        "id": identity,
        "action": data.action,
        "argument": data.argument,
        "confirmed": data.confirmed,
        "user_id": user.id,
        "created_at": time.time(),
        "nonce": secrets.token_hex(16),
    }
    audit(db, user.id, "operation.requested", identity, operation=data.action)
    db.commit()
    atomic_json(
        directory / f"{identity}.request.json",
        {"payload": payload, "signature": sign(payload, settings().secret_key)},
    )
    return {"id": identity, "status": "queued"}


@router.get("/operations")
def operations(user: User = Depends(require("system.manage"))):
    files = sorted(
        settings().operations_dir.glob("*.result.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return [json.loads(path.read_text()) for path in files[:30]]


@router.get("/backups")
def backups(user: User = Depends(require("system.manage"))):
    result = []
    for path in sorted(settings().backup_dir.glob("nexa-*.tar.gz"), reverse=True):
        metadata = path.with_name(path.name + ".json")
        if metadata.exists():
            result.append(
                {"name": path.name, "size": path.stat().st_size, **json.loads(metadata.read_text())}
            )
    return result


@router.get("/backups/{name}/download")
def download_backup(name: str, user: User = Depends(require("system.manage")), db: Session = Depends(get_db)):
    if not BACKUP_NAME.fullmatch(name):
        raise HTTPException(404, "not_found")
    path = settings().backup_dir / name
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, "not_found")
    audit(db, user.id, "backup.downloaded", name)
    db.commit()
    return FileResponse(
        path, filename=name, media_type="application/gzip", headers={"Cache-Control": "no-store"}
    )
