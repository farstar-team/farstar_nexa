"""BoxAPI's official Instagram callback and webhook endpoints.

The Meta integration has a different OAuth callback and signature format, so
BoxAPI events intentionally use separate routes.  The webhook accepts only
signed POST requests and turns each accepted event into the existing durable
incoming queue; it never processes the event inline.
"""

import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexa.db import get_db
from nexa.integration_config import integration_settings
from nexa.models import Account, User
from nexa.routes.workspace import enqueue
from nexa.security import audit, current_user, workspace

router = APIRouter(tags=["boxapi"])

_IDENTITY = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _redirect(status: str) -> RedirectResponse:
    return RedirectResponse("/?connection=" + status, status_code=303)


def _event_timestamp(value) -> str | None:
    try:
        number = float(value)
        # BoxAPI examples use milliseconds; accepting seconds keeps the parser
        # compatible with older payloads without changing the stored meaning.
        if number > 10_000_000_000:
            number /= 1000
        if number <= 0 or number > time.time() + 300:
            return None
        return datetime.fromtimestamp(number, UTC).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _valid_identity(value: object) -> str | None:
    text = str(value or "")
    return text if _IDENTITY.fullmatch(text) else None


def _normalize_messaging(account: Account, event_id: str, data: dict) -> list[dict]:
    result = []
    for item in data.get("messaging", []) if isinstance(data.get("messaging"), list) else []:
        if not isinstance(item, dict):
            continue
        sender = _valid_identity((item.get("sender") or {}).get("id"))
        message = item.get("message") or {}
        if not sender or not isinstance(message, dict) or message.get("is_echo"):
            continue
        quick_reply = message.get("quick_reply") or {}
        text = message.get("text") or quick_reply.get("title")
        message_id = _valid_identity(message.get("mid") or item.get("id") or event_id)
        if not message_id or not isinstance(text, str) or not text.strip():
            continue
        occurred_at = _event_timestamp(item.get("timestamp") or data.get("time"))
        if occurred_at is None:
            occurred_at = datetime.now(UTC).isoformat()
        result.append(
            {
                "account_id": account.id,
                "sender": sender,
                "text": text[:2000],
                "event_id": message_id,
                "occurred_at": occurred_at,
                "quick_reply_payload": str(quick_reply.get("payload", ""))[:256],
                "echo": bool(message.get("is_echo")),
            }
        )
    return result


def _normalize_comment(account: Account, data: dict) -> dict | None:
    media = data.get("media") if isinstance(data.get("media"), dict) else {}
    sender_data = data.get("from") or data.get("sender") or data.get("user") or {}
    sender = _valid_identity(sender_data.get("id") if isinstance(sender_data, dict) else sender_data)
    comment_id = _valid_identity(data.get("comment_id") or data.get("id"))
    media_id = _valid_identity(data.get("media_id") or media.get("id"))
    text = data.get("text") or data.get("message") or data.get("comment")
    if not sender or not comment_id or not media_id or not isinstance(text, str) or not text.strip():
        return None
    if sender == account.external_id:
        return None
    occurred_at = _event_timestamp(data.get("timestamp") or data.get("created_at") or data.get("time"))
    return {
        "account_id": account.id,
        "event_type": "comment",
        "event_id": comment_id,
        "sender": sender,
        "display_name": str(sender_data.get("username", ""))[:120]
        if isinstance(sender_data, dict)
        else "",
        "text": text[:2000],
        "media_external_id": media_id,
        "occurred_at": occurred_at or datetime.now(UTC).isoformat(),
    }


@router.get("/api/boxapi/instagram/callback")
def instagram_callback(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Finish BoxAPI's browser redirect and attach the returned page to Nexa."""

    query = request.query_params
    if query.get("status") != "success":
        audit(db, user.id, "boxapi.connection_failed", detail={"status": query.get("status", "")[:32]})
        db.commit()
        return _redirect("failed")
    account_id = _valid_identity(query.get("account_id"))
    username = str(query.get("username", "")).strip()[:120]
    if not account_id or not username:
        audit(db, user.id, "boxapi.connection_failed", detail={"reason": "invalid_callback"})
        db.commit()
        return _redirect("failed")
    try:
        ws = workspace(db, user)
        existing = db.scalar(
            select(Account).where(Account.provider == "boxapi", Account.external_id == account_id)
        )
        if existing and existing.workspace_id != ws.id:
            raise ValueError("account_already_owned")
        row = existing or Account(
            workspace_id=ws.id,
            provider="boxapi",
            external_id=account_id,
            name=username,
            credential=None,
            active=True,
        )
        row.name, row.active = username, True
        db.add(row)
        audit(db, user.id, "boxapi.connected", account_id)
        db.commit()
    except (ValueError, IntegrityError):
        db.rollback()
        audit(db, user.id, "boxapi.connection_failed", detail={"reason": "account_already_owned"})
        db.commit()
        return _redirect("failed")
    return _redirect("success")


@router.get("/webhooks/boxapi")
def webhook_probe():
    """A side-effect-free probe for HTTPS/domain checks in the BoxAPI panel."""

    return {"ok": True, "provider": "boxapi"}


@router.post("/webhooks/boxapi")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Verify and enqueue BoxAPI events without exposing secrets in responses/logs."""

    body = await request.body()
    config = integration_settings()
    secret = config.boxapi_webhook_secret.strip()
    if not secret:
        raise HTTPException(503, "boxapi_webhook_not_configured")
    signature = request.headers.get("X-BoxApi-Signature", "")
    timestamp = request.headers.get("X-BoxApi-Timestamp", "")
    header_event_id = request.headers.get("X-BoxApi-Event-Id", "")
    if not re.fullmatch(r"\d{1,16}", timestamp):
        raise HTTPException(401, "signature_invalid")
    if abs(time.time() - int(timestamp)) > 300:
        raise HTTPException(401, "signature_expired")
    expected = "sha256=" + hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "signature_invalid")
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        raise HTTPException(400, "invalid_event") from None
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid_event")
    event_id = _valid_identity(payload.get("event_id"))
    account_external_id = _valid_identity(payload.get("account_id"))
    event_type = str(payload.get("event_type", ""))[:64]
    if not event_id or not account_external_id or not event_type:
        raise HTTPException(400, "invalid_event")
    if header_event_id and not hmac.compare_digest(header_event_id, event_id):
        raise HTTPException(401, "event_id_mismatch")
    account = db.scalar(
        select(Account).where(
            Account.provider == "boxapi",
            Account.external_id == account_external_id,
            Account.active.is_(True),
        )
    )
    # A valid event for an account not yet attached to this workspace should be
    # acknowledged to stop provider retries, but must not create a new account.
    if not account:
        return {"ok": True, "accepted": False}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    events: list[tuple[str, dict]] = []
    if event_type == "messaging":
        events.extend((f"boxapi:{account.id}:{item['event_id']}", item) for item in _normalize_messaging(account, event_id, data))
    elif event_type in {"comments", "comment"}:
        item = _normalize_comment(account, data)
        if item:
            events.append((f"boxapi-comment:{account.id}:{item['event_id']}", item))
    for key, item in events:
        enqueue(db, key, "incoming", item)
    db.commit()
    return JSONResponse({"ok": True, "accepted": True, "events": len(events)})
