import json
import secrets
import time
import uuid
from typing import Literal
from urllib.parse import urlsplit

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from redis import Redis
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from nexa.config import settings, version
from nexa.db import get_db
from nexa.integration_config import FIELDS, integration_settings
from nexa.models import (
    Account,
    Audit,
    Automation,
    Execution,
    Job,
    Lead,
    Message,
    Notification,
    Product,
    SystemSetting,
    User,
)
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
    sender = config.smtp_from.strip()
    sender_local, sender_domain = (sender.rsplit("@", 1) if "@" in sender else ("", ""))
    base_domain = urlsplit(config.base_url).hostname or ""
    return {
        **{key: bool(getattr(config, key)) for key in sorted(FIELDS)},
        "public_urls": config.public_urls,
        "email_domain": sender_domain or base_domain,
        "email_local_part": sender_local,
    }


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
        if key == "telegram_channel_username" and value and not re.fullmatch(r"@?[A-Za-z0-9_]{5,64}", value):
            raise HTTPException(422, "validation_error")
        if key == "smtp_port":
            try:
                if not 1 <= int(value) <= 65535:
                    raise ValueError
            except ValueError:
                raise HTTPException(422, "validation_error") from None
        if key == "smtp_security" and value.lower() not in {"none", "starttls", "ssl"}:
            raise HTTPException(422, "validation_error")
        if key == "smtp_from":
            try:
                TypeAdapter(EmailStr).validate_python(value)
            except ValidationError:
                raise HTTPException(422, "validation_error") from None
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


@router.post("/email/test")
def email_test(
    data: dict,
    user: User = Depends(require("system.manage")),
    db: Session = Depends(get_db),
):
    password = str(data.get("password", ""))
    if not verify_password(password, user.password_hash):
        raise HTTPException(403, "invalid_credentials")
    recipient = str(data.get("to", user.email))
    try:
        TypeAdapter(EmailStr).validate_python(recipient)
    except ValidationError:
        raise HTTPException(422, "validation_error") from None
    from nexa.email_service import send_email

    try:
        send_email(recipient, "آزمایش ایمیل Farstar Nexa", "این پیام برای بررسی تنظیمات ایمیل پنل ارسال شده است.")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception:
        raise HTTPException(502, "email_delivery_failed") from None
    audit(db, user.id, "email.test_sent")
    db.commit()
    return {"ok": True}


class ContentInput(BaseModel):
    values: dict[str, str]


@router.get("/content")
def get_content(user: User = Depends(require("system.manage")), db: Session = Depends(get_db)):
    from nexa.routes.content import CONTENT_DEFAULTS, values

    return {"values": values(db), "defaults": CONTENT_DEFAULTS}


@router.put("/content")
def save_content(
    data: ContentInput,
    user: User = Depends(require("system.manage")),
    db: Session = Depends(get_db),
):
    from nexa.routes.content import CONTENT_DEFAULTS

    if not set(data.values) <= set(CONTENT_DEFAULTS) or any(len(value) > 2000 for value in data.values.values()):
        raise HTTPException(422, "validation_error")
    for key, value in data.values.items():
        if not value.strip():
            continue
        row = db.get(SystemSetting, key)
        if row:
            row.value = value.strip()
        else:
            db.add(SystemSetting(key=key, value=value.strip()))
    audit(db, user.id, "content.updated", fields=sorted(data.values))
    db.commit()
    return {"ok": True}


class AdminMessage(BaseModel):
    user_id: str | None = None
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=5000)
    channels: list[Literal["panel", "email", "telegram"]] = Field(min_length=1, max_length=3)


@router.post("/messages", status_code=202)
def send_admin_message(
    data: AdminMessage,
    user: User = Depends(require("system.manage")),
    db: Session = Depends(get_db),
):
    if data.user_id == "*":
        targets = list(db.scalars(select(User).where(User.active.is_(True), User.id != user.id)))
    else:
        target = db.get(User, data.user_id or "")
        if not target or not target.active:
            raise HTTPException(404, "not_found")
        targets = [target]
    channels = list(dict.fromkeys(data.channels))
    for target in targets:
        for channel in channels:
            notification = Notification(
                user_id=target.id,
                title=data.title.strip(),
                body=data.body.strip(),
                channel=channel,
                status="sent" if channel == "panel" else "queued",
            )
            db.add(notification)
            db.flush()
            if channel in {"email", "telegram"}:
                db.add(
                    Job(
                        key=f"notification:{notification.id}",
                        kind="notification_" + channel,
                        payload={"notification_id": notification.id},
                    )
                )
    audit(db, user.id, "notification.broadcast" if data.user_id == "*" else "notification.sent", data.user_id or "", channels=channels, recipients=len(targets))
    db.commit()
    return {"ok": True, "channels": channels, "recipients": len(targets)}


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
            "products": Product,
            "leads": Lead,
            "automations": Automation,
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
