import hashlib
import hmac
import json
import time

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
