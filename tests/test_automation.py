from datetime import timedelta

import pytest
from conftest import sign_in
from fastapi.testclient import TestClient
from nexa.automation import matches
from nexa.db import utcnow
from nexa.main import app
from nexa.models import Execution, Job, Message
from nexa.providers import PROVIDERS, DeliveryUnknown
from nexa.worker import recover_stale, run_one
from sqlalchemy import func, select


@pytest.mark.parametrize(
    "text,keywords,mode,expected",
    [
        ("قیمت", ["قیمت"], "exact", True),
        ("قیمت محصول", ["قیمت"], "exact", False),
        ("لطفاً قیمت", ["قیمت"], "contains", True),
        ("قیمت محصول", ["قیمت"], "starts_with", True),
        ("محصول قیمت", ["قیمت"], "starts_with", False),
        ("كيف", ["کیف"], "exact", True),
        (" Hello ", ["hello"], "exact", True),
        ("anything", [""], "contains", False),
    ],
)
def test_keyword_modes(text, keywords, mode, expected):
    assert matches(text, keywords, mode) is expected


def simulate(client, account, event="event-1", text="قیمت", sender="customer"):
    return client.post(
        "/api/messages/simulate",
        json={"account_id": account["id"], "sender": sender, "text": text, "event_id": event},
    )


def drain():
    for _ in range(20):
        if not run_one():
            return
    raise AssertionError("Queue did not drain")


def test_full_pipeline_and_duplicate_event(signed, account, rule, db):
    assert simulate(signed, account).json()["accepted"]
    assert not simulate(signed, account).json()["accepted"]
    drain()
    rows = list(db.scalars(select(Message).order_by(Message.created_at)))
    assert len(rows) == 2
    assert rows[0].direction == "in"
    assert rows[1].direction == "out" and rows[1].status == "sent"
    assert rows[1].text == rule["response"]
    assert db.scalar(select(func.count()).select_from(Execution)) == 1
    conversations = signed.get("/api/conversations").json()
    assert len(signed.get(f"/api/conversations/{conversations[0]['id']}/messages").json()) == 2
    assert signed.get("/api/executions").json()[0]["status"] == "sent"


def test_cooldown(signed, account, rule, db):
    simulate(signed, account)
    drain()
    simulate(signed, account, "event-2")
    drain()
    assert db.scalar(select(func.count()).select_from(Message).where(Message.direction == "out")) == 1
    assert "cooldown" in list(db.scalars(select(Execution.status)))


def test_unknown_delivery_is_not_retried(signed, account, rule, db, monkeypatch):
    calls = []

    def uncertain(*args):
        calls.append(True)
        raise DeliveryUnknown()

    monkeypatch.setattr(PROVIDERS["instagram_mock"], "send", uncertain)
    simulate(signed, account)
    drain()
    drain()
    assert len(calls) == 1
    assert db.scalar(select(Execution.status)) == "unknown"


def test_tenant_isolation(signed, account, rule):
    simulate(signed, account)
    drain()
    conversation = signed.get("/api/conversations").json()[0]["id"]
    with TestClient(app) as other:
        sign_in(other, "bob")
        assert other.get("/api/accounts").json() == []
        assert other.get("/api/automations").json() == []
        assert other.get("/api/executions").json() == []
        assert other.get("/api/conversations").json() == []
        assert other.get("/api/conversations/" + conversation + "/messages").status_code == 404
        assert other.patch("/api/automations/" + rule["id"], json={"enabled": False}).status_code == 404
        assert other.delete("/api/accounts/" + account["id"]).status_code == 404
        assert simulate(other, account).status_code == 404
        assert (
            other.post(
                "/api/automations",
                json={"account_id": account["id"], "name": "attack", "keywords": ["x"], "response": "x"},
            ).status_code
            == 404
        )


def test_echo_does_not_create_messages(signed, account, db):
    db.add(
        Job(
            key="echo:1",
            kind="incoming",
            payload={"account_id": account["id"], "sender": "self", "text": "قیمت", "echo": True},
        )
    )
    db.commit()
    drain()
    assert db.scalar(select(func.count()).select_from(Message)) == 0


def test_stale_send_is_quarantined(signed, account, rule, db):
    simulate(signed, account)
    assert run_one()
    job = db.scalar(select(Job).where(Job.kind == "send"))
    job.status, job.locked_at = "running", utcnow() - timedelta(minutes=10)
    db.commit()
    recover_stale(db)
    db.refresh(job)
    assert job.status == "unknown"
    assert not run_one()
