from nexa.models import Notification, User


def test_support_ticket_and_reply(signed):
    created = signed.post(
        "/api/support/tickets",
        json={"subject": "راهنمای اتصال", "message": "چطور اتصال را فعال کنم؟", "channel": "live_chat"},
    )
    assert created.status_code == 201
    identity = created.json()["id"]
    detail = signed.get(f"/api/support/tickets/{identity}")
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 1
    reply = signed.post(f"/api/support/tickets/{identity}/messages", json={"body": "ممنون"})
    assert reply.status_code == 201


def test_support_ticket_code_states_and_close(signed):
    created = signed.post(
        "/api/support/tickets",
        json={"subject": "پیگیری سفارش", "message": "لطفاً راهنمایی کنید"},
    )
    assert created.status_code == 201
    ticket = created.json()
    assert ticket["ticket_code"].startswith("NX-")
    assert ticket["status"] == "waiting_support"
    assert signed.get("/api/support/tickets?q=" + ticket["ticket_code"]).json()[0]["id"] == ticket["id"]
    second = signed.post(
        f"/api/support/tickets/{ticket['id']}/messages", json={"body": "هنوز منتظر پاسخ هستم"}
    )
    assert second.status_code == 201
    assert signed.get(f"/api/support/tickets/{ticket['id']}").json()["status"] == "waiting_support"
    closed = signed.patch(f"/api/support/tickets/{ticket['id']}", json={"status": "closed"})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    blocked = signed.post(
        f"/api/support/tickets/{ticket['id']}/messages", json={"body": "پیام جدید"}
    )
    assert blocked.status_code == 409


def test_public_content_can_be_edited_by_owner(owner):
    assert owner.get("/api/content").status_code == 200
    result = owner.put("/api/admin/content", json={"values": {"landing.cta": "شروع امن"}})
    assert result.status_code == 200
    assert owner.get("/api/content").json()["landing.cta"] == "شروع امن"


def test_panel_notification_is_created_without_external_delivery(owner, db):
    target = User(
        username="notify_target",
        email="notify_target@example.com",
        password_hash="unused",
        role="USER",
    )
    db.add(target)
    db.flush()
    db.commit()
    result = owner.post(
        "/api/admin/messages",
        json={"user_id": target.id, "title": "اطلاعیه", "body": "متن", "channels": ["panel"]},
    )
    assert result.status_code == 202
    assert db.query(Notification).filter_by(user_id=target.id, channel="panel", status="sent").count() == 1
