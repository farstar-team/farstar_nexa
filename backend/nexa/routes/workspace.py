import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexa.config import settings
from nexa.db import get_db, utcnow
from nexa.integration_config import integration_settings
from nexa.models import Account, Audit, Automation, Conversation, Execution, Job, Message, TelegramLink, User
from nexa.security import audit, current_user, issue_token, owned, rate_limit, workspace

router = APIRouter(prefix="/api", tags=["workspace"])


def serialize(row, fields):
    result = {key: getattr(row, key) for key in fields.split()}
    for key, value in result.items():
        if hasattr(value, "isoformat"):
            result[key] = value.isoformat() + "Z"
    return result


ACCOUNT_FIELDS = "id provider external_id name active created_at"
RULE_FIELDS = "id account_id name enabled keywords match_mode response priority cooldown_seconds created_at"


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace(db, user)
    counts = {
        name: db.scalar(select(func.count()).select_from(model).where(model.workspace_id == ws.id))
        for name, model in {
            "accounts": Account,
            "messages": Message,
            "automations": Automation,
            "executions": Execution,
        }.items()
    }
    days = []
    for offset in range(6, -1, -1):
        start = (utcnow() - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        count = db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.workspace_id == ws.id,
                Message.direction == "in",
                Message.created_at >= start,
                Message.created_at < start + timedelta(days=1),
            )
        )
        days.append({"date": start.isoformat() + "Z", "count": count})
    return {"counts": counts, "activity": days}


@router.get("/accounts")
def accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        serialize(row, ACCOUNT_FIELDS)
        for row in db.scalars(
            select(Account)
            .where(Account.workspace_id == workspace(db, user).id)
            .order_by(Account.created_at.desc())
        )
    ]


class NewAccount(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/accounts/mock", status_code=201)
def mock_account(data: NewAccount, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings().mock_mode:
        raise HTTPException(403, "mock_disabled")
    row = Account(
        workspace_id=workspace(db, user).id,
        provider="instagram_mock",
        external_id=str(uuid.uuid4()),
        name=data.name,
    )
    db.add(row)
    db.flush()
    audit(db, user.id, "account.mock_created", row.id)
    db.commit()
    return serialize(row, ACCOUNT_FIELDS)


@router.delete("/accounts/{identity}")
def disconnect(identity: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = owned(db, Account, identity, workspace(db, user).id)
    row.active, row.credential = False, None
    audit(db, user.id, "account.disconnected", row.id)
    db.commit()
    return {"ok": True}


class RuleInput(BaseModel):
    account_id: str
    name: str = Field(min_length=1, max_length=120)
    keywords: list[str] = Field(min_length=1, max_length=30)
    match_mode: Literal["exact", "contains", "starts_with"] = "contains"
    response: str = Field(min_length=1, max_length=1000)
    priority: int = Field(default=0, ge=0, le=1000)
    cooldown_seconds: int = Field(default=60, ge=2, le=86400)
    enabled: bool = True

    @field_validator("keywords")
    @classmethod
    def valid_keywords(cls, value):
        if any(not k.strip() or len(k) > 120 for k in value):
            raise ValueError("invalid_keywords")
        return [k.strip() for k in value]


@router.get("/automations")
def rules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        serialize(row, RULE_FIELDS)
        for row in db.scalars(
            select(Automation)
            .where(Automation.workspace_id == workspace(db, user).id)
            .order_by(Automation.priority.desc())
        )
    ]


@router.post("/automations", status_code=201)
def create_rule(data: RuleInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace(db, user)
    account = owned(db, Account, data.account_id, ws.id)
    if not account.active:
        raise HTTPException(400, "account_inactive")
    row = Automation(workspace_id=ws.id, **data.model_dump())
    db.add(row)
    db.flush()
    audit(db, user.id, "automation.created", row.id)
    db.commit()
    return serialize(row, RULE_FIELDS)


class Toggle(BaseModel):
    enabled: bool


@router.patch("/automations/{identity}")
def toggle_rule(
    identity: str, data: Toggle, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = owned(db, Automation, identity, workspace(db, user).id)
    row.enabled = data.enabled
    audit(db, user.id, "automation.toggle", row.id, enabled=data.enabled)
    db.commit()
    return serialize(row, RULE_FIELDS)


@router.put("/automations/{identity}")
def edit_rule(
    identity: str, data: RuleInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    ws = workspace(db, user)
    row = owned(db, Automation, identity, ws.id)
    owned(db, Account, data.account_id, ws.id)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    audit(db, user.id, "automation.edited", row.id)
    db.commit()
    return serialize(row, RULE_FIELDS)


class TestMessage(BaseModel):
    account_id: str
    sender: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=100)


def enqueue(db: Session, key: str, kind: str, payload: dict) -> bool:
    try:
        with db.begin_nested():
            db.add(Job(key=key, kind=kind, payload=payload))
            db.flush()
        return True
    except IntegrityError:
        return False


@router.post("/messages/simulate", status_code=202)
def simulate(data: TestMessage, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings().mock_mode:
        raise HTTPException(403, "mock_disabled")
    rate_limit("simulate:" + user.id, 30, 60)
    row = owned(db, Account, data.account_id, workspace(db, user).id)
    if row.provider != "instagram_mock" or not row.active:
        raise HTTPException(400, "invalid_mock_account")
    accepted = enqueue(db, f"mock:{row.id}:{data.event_id}", "incoming", data.model_dump())
    db.commit()
    return {"accepted": accepted}


@router.get("/conversations")
def conversations(
    user: User = Depends(current_user), db: Session = Depends(get_db), offset: int = Query(0, ge=0)
):
    return [
        serialize(row, "id account_id sender_id created_at")
        for row in db.scalars(
            select(Conversation)
            .where(Conversation.workspace_id == workspace(db, user).id)
            .order_by(Conversation.created_at.desc())
            .offset(offset)
            .limit(100)
        )
    ]


@router.get("/conversations/{identity}/messages")
def messages(identity: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned(db, Conversation, identity, workspace(db, user).id)
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == identity)
            .order_by(Message.created_at.desc())
            .limit(200)
        )
    )
    return [serialize(row, "id direction text status created_at") for row in reversed(rows)]


@router.get("/executions")
def executions(
    user: User = Depends(current_user), db: Session = Depends(get_db), offset: int = Query(0, ge=0)
):
    return [
        serialize(row, "id automation_id status detail created_at")
        for row in db.scalars(
            select(Execution)
            .where(Execution.workspace_id == workspace(db, user).id)
            .order_by(Execution.created_at.desc())
            .offset(offset)
            .limit(100)
        )
    ]


@router.get("/activity")
def activity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        serialize(row, "id action target created_at")
        for row in db.scalars(
            select(Audit).where(Audit.user_id == user.id).order_by(Audit.created_at.desc()).limit(100)
        )
    ]


@router.get("/telegram")
def telegram_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == user.id))
    return {
        "linked": bool(link),
        "configured": bool(integration_settings().telegram_bot_token),
        "username": integration_settings().telegram_bot_username,
    }


@router.post("/telegram/link")
def telegram_link(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not integration_settings().telegram_bot_token or not integration_settings().telegram_bot_username:
        raise HTTPException(503, "telegram_not_configured")
    token = issue_token(db, user.id, "telegram")
    audit(db, user.id, "telegram.link_requested")
    db.commit()
    return {
        "url": f"https://t.me/{integration_settings().telegram_bot_username}?start={token}",
        "expires_in": 600,
    }


@router.delete("/telegram/link")
def telegram_unlink(user: User = Depends(current_user), db: Session = Depends(get_db)):
    link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == user.id))
    if link:
        db.delete(link)
    # Invalidate pending links as well as the existing association.
    from nexa.models import OneTimeToken

    for token in db.scalars(
        select(OneTimeToken).where(
            OneTimeToken.user_id == user.id,
            OneTimeToken.purpose == "telegram",
            OneTimeToken.consumed_at.is_(None),
        )
    ):
        token.consumed_at = utcnow()
    audit(db, user.id, "telegram.unlinked")
    db.commit()
    return {"ok": True}
