from datetime import timedelta

import pytest
from sqlalchemy import select
from conftest import PASSWORD
from nexa.db import utcnow
from nexa.models import OneTimeToken, TelegramLink, User
from nexa.security import consume_token, decrypt, digest, encrypt, issue_token
from nexa.telegram import handle_update


def test_integration_config_is_encrypted_and_never_returned(owner, db):
    from nexa.models import SystemSetting

    secret = "test-provider-secret-not-real"
    response = owner.put(
        "/api/admin/integrations", json={"password": PASSWORD, "values": {"meta_app_secret": secret}}
    )
    assert response.status_code == 200
    row = db.get(SystemSetting, "meta_app_secret")
    assert row.value != secret and decrypt(row.value) == secret
    response = owner.get("/api/admin/integrations")
    assert response.json()["meta_app_secret"] is True
    assert secret not in response.text


def test_telegram_webhook_does_not_store_plain_link_token(client, db):
    from nexa.config import settings
    from nexa.models import Job

    payload = {"update_id": 123, "message": {"text": "/start private-one-time-token"}}
    assert (
        client.post(
            "/webhooks/telegram",
            json=payload,
            headers={"x-telegram-bot-api-secret-token": settings().telegram_webhook_secret},
        ).status_code
        == 200
    )
    job = db.scalar(select(Job))
    assert "private-one-time-token" not in str(job.payload)


def test_encrypted_credentials():
    encrypted = encrypt("private-token-value")
    assert "private-token-value" not in encrypted
    assert decrypt(encrypted) == "private-token-value"


def test_one_time_expiry_and_consumption(signed, db):
    user = db.scalar(select(User))
    token = issue_token(db, user.id, "telegram")
    db.commit()
    assert db.scalar(select(OneTimeToken)).token_hash == digest(token)
    consume_token(db, token, "telegram")
    db.commit()
    with pytest.raises(ValueError):
        consume_token(db, token, "telegram")
    expired = issue_token(db, user.id, "telegram")
    db.commit()
    row = db.scalar(select(OneTimeToken).where(OneTimeToken.token_hash == digest(expired)))
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(ValueError):
        consume_token(db, expired, "telegram")


def test_telegram_link_private_chat_and_unlink(signed, db, monkeypatch):
    calls = []
    monkeypatch.setattr("nexa.telegram.bot_call", lambda method, payload: calls.append((method, payload)))
    user = db.scalar(select(User))
    token = issue_token(db, user.id, "telegram")
    db.commit()
    data = {"message": {"from": {"id": 42}, "chat": {"id": 42, "type": "group"}, "text": "/start " + token}}
    handle_update(db, data)
    assert db.scalar(select(TelegramLink)) is None
    data["message"]["chat"]["type"] = "private"
    handle_update(db, data)
    assert db.scalar(select(TelegramLink)).user_id == user.id
    assert calls[-1][0] == "sendMessage"
    assert signed.delete("/api/telegram/link").status_code == 200
    db.expire_all()
    assert db.scalar(select(TelegramLink)) is None
    with pytest.raises(ValueError):
        consume_token(db, token, "telegram")


def test_password_recovery_revokes_session(signed, db):
    user = db.scalar(select(User))
    token = issue_token(db, user.id, "password_reset")
    db.commit()
    assert (
        signed.post(
            "/api/auth/reset-password", json={"token": token, "password": PASSWORD + "reset"}
        ).status_code
        == 200
    )
    assert signed.get("/api/auth/me").status_code == 401
    assert (
        signed.post(
            "/api/auth/reset-password", json={"token": token, "password": PASSWORD + "reset"}
        ).status_code
        == 400
    )
