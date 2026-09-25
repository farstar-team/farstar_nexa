import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from nexa.db import get_db
from nexa.integration_config import integration_settings
from nexa.models import Account
from nexa.routes.workspace import enqueue
from nexa.security import encrypt

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/meta")
def verify_meta(request: Request):
    query = request.query_params
    secret = integration_settings().meta_verify_token
    if (
        not secret
        or query.get("hub.mode") != "subscribe"
        or not hmac.compare_digest(query.get("hub.verify_token", ""), secret)
    ):
        raise HTTPException(403, "verification_failed")
    return PlainTextResponse(query.get("hub.challenge", ""))


@router.post("/meta")
async def meta(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    secret = integration_settings().meta_app_secret
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected):
        raise HTTPException(403, "signature_invalid")
    try:
        data = json.loads(body)
        if data.get("object") != "instagram":
            return {"ok": True}
        for entry in data.get("entry", []):
            account = db.scalar(
                select(Account).where(
                    Account.provider == "instagram",
                    Account.external_id == str(entry["id"]),
                    Account.active.is_(True),
                )
            )
            if not account:
                continue
            changes = entry.get("changes", [])
            if entry.get("field") == "comments":
                changes = [*changes, entry]
            for change in changes:
                if change.get("field") != "comments":
                    continue
                value = change.get("value", {})
                comment_id = str(value.get("id") or value.get("comment_id", ""))
                sender = str(value.get("from", {}).get("id", ""))
                media_id = str(value.get("media", {}).get("id", ""))
                if (
                    not all(re.fullmatch(r"[0-9]{1,128}", v) for v in (comment_id, sender, media_id))
                    or sender == account.external_id
                ):
                    continue
                if not value.get("text") or value.get("media", {}).get("media_product_type") not in {
                    "FEED",
                    "REELS",
                }:
                    continue
                enqueue(
                    db,
                    f"meta-comment:{account.id}:{comment_id}",
                    "incoming",
                    {
                        "account_id": account.id,
                        "event_type": "comment",
                        "event_id": comment_id,
                        "sender": sender,
                        "display_name": str(value.get("from", {}).get("username", ""))[:120],
                        "text": str(value["text"])[:2000],
                        "media_external_id": media_id,
                    },
                )
            for event in entry.get("messaging", []):
                message = event.get("message", {})
                sender = str(event.get("sender", {}).get("id", ""))
                if not message.get("text") or not message.get("mid") or message.get("is_echo"):
                    continue
                if not sender or sender == account.external_id:
                    continue
                # Refuse events outside the messaging window, including future timestamps.
                age = time.time() - float(event.get("timestamp", 0)) / 1000
                if age > 86400 or age < -300:
                    continue
                enqueue(
                    db,
                    f"meta:{account.id}:{message['mid']}",
                    "incoming",
                    {
                        "account_id": account.id,
                        "sender": sender,
                        "text": str(message["text"])[:2000],
                        "event_id": str(message["mid"])[:128],
                        "occurred_at": datetime.fromtimestamp(
                            float(event["timestamp"]) / 1000, UTC
                        ).isoformat(),
                    },
                )
        db.commit()
    except (ValueError, KeyError, TypeError, AttributeError):
        db.rollback()
        raise HTTPException(400, "invalid_event") from None
    return {"ok": True}


@router.post("/telegram")
async def telegram(request: Request, db: Session = Depends(get_db)):
    secret = integration_settings().telegram_webhook_secret
    if not secret or not hmac.compare_digest(
        request.headers.get("x-telegram-bot-api-secret-token", ""), secret
    ):
        raise HTTPException(403, "signature_invalid")
    try:
        data = await request.json()
        update_id = int(data["update_id"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "invalid_event") from None
    enqueue(db, f"telegram:{update_id}", "telegram", {"encrypted": encrypt(json.dumps(data))})
    db.commit()
    return {"ok": True}
