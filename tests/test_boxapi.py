import hashlib
import hmac
import json
import time

from nexa.config import settings
from nexa.models import Account, Job


def test_boxapi_authorize_returns_configured_login_url(signed, monkeypatch):
    login_url = "https://api.sendbox.chat/instagram-oauth?token=login-token"
    monkeypatch.setattr(settings(), "boxapi_login_url", login_url)
    response = signed.post("/api/boxapi/authorize")
    assert response.status_code == 200
    assert response.json() == {"url": login_url}


def test_boxapi_authorize_requires_login_url(signed, monkeypatch):
    monkeypatch.setattr(settings(), "boxapi_login_url", "")
    response = signed.post("/api/boxapi/authorize")
    assert response.status_code == 503
    assert response.json() == {"detail": "boxapi_not_configured"}


def test_boxapi_callback_attaches_page_to_current_workspace(signed, db):
    response = signed.get(
        "/api/boxapi/instagram/callback?status=success&username=shop_page&account_id=box-page-1",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?connection=success"
    row = db.query(Account).filter_by(provider="boxapi", external_id="box-page-1").one()
    assert row.name == "shop_page"
    assert row.active is True


def test_boxapi_callback_rejects_incomplete_result(signed, db):
    response = signed.get(
        "/api/boxapi/instagram/callback?status=failed&message=denied", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?connection=failed"
    assert db.query(Account).filter_by(provider="boxapi").count() == 0


def test_boxapi_webhook_verifies_signature_and_enqueues(signed, db, monkeypatch):
    signed.get(
        "/api/boxapi/instagram/callback?status=success&username=shop_page&account_id=box-page-1",
        follow_redirects=False,
    )
    secret = "webhook-secret-for-test"
    monkeypatch.setattr(settings(), "boxapi_webhook_secret", secret)
    timestamp = str(int(time.time()))
    payload = {
        "event_id": "evt-1",
        "event_type": "messaging",
        "account_id": "box-page-1",
        "data": {
            "messaging": [
                {
                    "sender": {"id": "customer-1"},
                    "timestamp": int(timestamp) * 1000,
                    "message": {"mid": "mid-1", "text": "قیمت"},
                }
            ]
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    response = signed.post(
        "/webhooks/boxapi",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-BoxApi-Signature": signature,
            "X-BoxApi-Timestamp": timestamp,
            "X-BoxApi-Event-Id": "evt-1",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "accepted": True, "events": 1}
    job = db.query(Job).filter(Job.key.like("boxapi:%:mid-1")).one()
    assert job.kind == "incoming"
    assert job.payload["text"] == "قیمت"


def test_boxapi_webhook_rejects_invalid_signature(signed, monkeypatch):
    monkeypatch.setattr(settings(), "boxapi_webhook_secret", "webhook-secret-for-test")
    response = signed.post(
        "/webhooks/boxapi",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-BoxApi-Signature": "sha256=invalid",
            "X-BoxApi-Timestamp": str(int(time.time())),
        },
    )
    assert response.status_code == 401


def test_boxapi_webhook_requires_secret(signed, monkeypatch):
    monkeypatch.setattr(settings(), "boxapi_webhook_secret", "")
    response = signed.post("/webhooks/boxapi", content=b"{}")
    assert response.status_code == 503
    assert response.json() == {"detail": "boxapi_webhook_not_configured"}
