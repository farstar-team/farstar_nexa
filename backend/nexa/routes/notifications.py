from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from nexa.db import get_db, utcnow
from nexa.models import Notification, User
from nexa.security import current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def notification_dict(row: Notification) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "channel": row.channel,
        "status": row.status,
        "read": bool(row.read_at),
        "created_at": row.created_at.replace(tzinfo=UTC).isoformat(),
    }


@router.get("")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id, Notification.channel == "panel")
        .order_by(Notification.created_at.desc())
        .limit(100)
    ).all()
    return [notification_dict(row) for row in rows]


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if not row:
        raise HTTPException(404, "not_found")
    row.read_at = row.read_at or utcnow()
    db.commit()
    return {"ok": True}
