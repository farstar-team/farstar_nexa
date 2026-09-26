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
