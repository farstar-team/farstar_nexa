import hashlib
import hmac
import json
import time

from nexa.config import settings
from nexa.models import Account, Job
from sqlalchemy import func, select


def test_meta_verification(client):
    assert (
        client.get(
            "/webhooks/meta",
            params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "123"},
        ).status_code
        == 403
    )
    response = client.get(
        "/webhooks/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings().meta_verify_token,
            "hub.challenge": "123",
        },
    )
    assert response.status_code == 200 and response.text == "123"


def test_meta_signature_idempotency_and_replay(signed, account, db):
    row = db.get(Account, account["id"])
    row.provider, row.external_id = "instagram", "123456"
    db.commit()
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "123456",
                "messaging": [
                    {
                        "sender": {"id": "98765"},
                        "timestamp": int(time.time() * 1000),
                        "message": {"mid": "m-1", "text": "قیمت"},
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(settings().meta_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    assert (
        signed.post("/webhooks/meta", content=raw, headers={"x-hub-signature-256": "bad"}).status_code == 403
    )
    for _ in range(2):
        assert (
            signed.post("/webhooks/meta", content=raw, headers={"x-hub-signature-256": signature}).status_code
            == 200
        )
    assert db.scalar(select(func.count()).select_from(Job)) == 1
    payload["entry"][0]["messaging"][0]["timestamp"] = 1
    payload["entry"][0]["messaging"][0]["message"]["mid"] = "stale"
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(settings().meta_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    assert (
        signed.post("/webhooks/meta", content=raw, headers={"x-hub-signature-256": signature}).status_code
        == 200
    )
    assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_telegram_secret_and_idempotency(client, db):
    assert client.post("/webhooks/telegram", json={"update_id": 100}).status_code == 403
    for _ in range(2):
        assert (
            client.post(
                "/webhooks/telegram",
                json={"update_id": 100},
                headers={"x-telegram-bot-api-secret-token": settings().telegram_webhook_secret},
            ).status_code
            == 200
        )
    assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_payload_limit(client):
    assert client.post("/webhooks/meta", content=b"x" * (1024 * 1024 + 1)).status_code == 413
