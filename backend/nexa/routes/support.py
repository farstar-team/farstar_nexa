import secrets
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from nexa.db import get_db, utcnow
from nexa.models import SupportMessage, SupportTicket, User
from nexa.security import audit, current_user, workspace

router = APIRouter(prefix="/api/support", tags=["support"])


class NewTicket(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=1, max_length=5000)


class NewMessage(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class TicketStatus(BaseModel):
    status: str = Field(pattern="^(waiting_support|waiting_user|waiting_new_reply|closed)$")


STATUS_ALIASES = {"open": "waiting_support", "pending": "waiting_user", "resolved": "closed"}


def new_ticket_code(db: Session) -> str:
    for _ in range(10):
        value = "NX-" + secrets.token_hex(5).upper()
        if not db.scalar(select(SupportTicket.id).where(SupportTicket.ticket_code == value)):
            return value
    raise HTTPException(503, "ticket_code_unavailable")


def ticket_visible(db: Session, ticket_id: str, user: User) -> SupportTicket:
    row = db.get(SupportTicket, ticket_id)
    if not row or (row.user_id != user.id and user.role not in {"ADMIN", "SUPER_ADMIN"}):
        raise HTTPException(404, "not_found")
    return row


def message_dict(row: SupportMessage) -> dict:
    return {
        "id": row.id,
        "body": row.body,
        "author_role": row.author_role,
        "created_at": row.created_at.replace(tzinfo=UTC).isoformat(),
    }


def ticket_dict(row: SupportTicket, include_messages=False) -> dict:
    result = {
        "id": row.id,
        "ticket_code": row.ticket_code,
        "subject": row.subject,
        "status": STATUS_ALIASES.get(row.status, row.status),
        "priority": row.priority,
        "channel": row.channel,
        "user_id": row.user_id,
        "created_at": row.created_at.replace(tzinfo=UTC).isoformat(),
        "updated_at": row.updated_at.replace(tzinfo=UTC).isoformat(),
    }
    if include_messages:
        result["messages"] = [message_dict(message) for message in row._messages]
    return result


def load_messages(db: Session, ticket: SupportTicket):
    ticket._messages = list(
        db.scalars(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == ticket.id)
            .order_by(SupportMessage.created_at.asc())
        )
    )


@router.get("/tickets")
def tickets(
    q: str = Query(default="", max_length=80),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(SupportTicket)
    if user.role not in {"ADMIN", "SUPER_ADMIN"}:
        query = query.where(SupportTicket.user_id == user.id)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where((SupportTicket.ticket_code.ilike(term)) | (SupportTicket.subject.ilike(term)))
    rows = db.scalars(query.order_by(SupportTicket.updated_at.desc()).offset(offset).limit(20)).all()
    return [ticket_dict(row) for row in rows]


@router.post("/tickets", status_code=201)
def create_ticket(data: NewTicket, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = SupportTicket(
        workspace_id=workspace(db, user).id,
        user_id=user.id,
        ticket_code=new_ticket_code(db),
        subject=data.subject.strip(),
        channel="ticket",
        status="waiting_support",
    )
    db.add(row)
    db.flush()
    db.add(SupportMessage(ticket_id=row.id, author_id=user.id, author_role="user", body=data.message.strip()))
    audit(db, user.id, "support.ticket_created", row.id)
    db.commit()
    return ticket_dict(row)


@router.get("/tickets/{ticket_id}")
def ticket(ticket_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = ticket_visible(db, ticket_id, user)
    load_messages(db, row)
    return ticket_dict(row, include_messages=True)


@router.post("/tickets/{ticket_id}/messages", status_code=201)
def add_message(
    ticket_id: str,
    data: NewMessage,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = ticket_visible(db, ticket_id, user)
    if row.status == "closed":
        raise HTTPException(409, "ticket_closed")
    role = "admin" if user.role in {"ADMIN", "SUPER_ADMIN"} else "user"
    item = SupportMessage(ticket_id=row.id, author_id=user.id, author_role=role, body=data.body.strip())
    row.updated_at = utcnow()
    if role == "admin":
        row.status = "waiting_user"
    else:
        prior_admin = db.scalar(
            select(SupportMessage.id).where(
                SupportMessage.ticket_id == row.id, SupportMessage.author_role == "admin"
            )
        )
        row.status = "waiting_new_reply" if prior_admin else "waiting_support"
    db.add(item)
    audit(db, user.id, "support.message_added", row.id, role=role)
    db.commit()
    return message_dict(item)


@router.patch("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    data: TicketStatus,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    is_admin = user.role in {"ADMIN", "SUPER_ADMIN"}
    if not is_admin and data.status != "closed":
        raise HTTPException(403, "forbidden")
    row = ticket_visible(db, ticket_id, user)
    current = STATUS_ALIASES.get(row.status, row.status)
    if current == "closed" and data.status != "closed":
        raise HTTPException(409, "ticket_closed")
    row.status = data.status
    row.updated_at = utcnow()
    audit(db, user.id, "support.ticket_status", row.id, status=data.status)
    db.commit()
    return ticket_dict(row)
