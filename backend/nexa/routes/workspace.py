import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexa.commerce_schema import CommentInput, FlowInput, aware
from nexa.config import settings
from nexa.db import get_db, utcnow
from nexa.integration_config import integration_settings
from nexa.models import (
    Account,
    ActionExecution,
    Audit,
    Automation,
    Conversation,
    Execution,
    InstagramMedia,
    Job,
    Message,
    Product,
    TelegramLink,
    User,
)
from nexa.security import audit, current_user, issue_token, owned, rate_limit, workspace

router = APIRouter(prefix="/api", tags=["workspace"])


def serialize(row, fields):
    result = {key: getattr(row, key) for key in fields.split()}
    for key, value in result.items():
        if hasattr(value, "isoformat"):
            result[key] = aware(value).isoformat()
        elif isinstance(value, Decimal):
            result[key] = str(value)
    return result


ACCOUNT_FIELDS = "id provider external_id name active created_at"
RULE_FIELDS = "id account_id name enabled status trigger_type keywords match_mode response priority cooldown_seconds product_id scope media_ids flow created_at"


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
    dry_run_only: bool = False


@router.post("/accounts/mock", status_code=201)
def mock_account(data: NewAccount, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings().mock_mode and not data.dry_run_only:
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
    keywords: list[str] = Field(default_factory=list, max_length=30)
    match_mode: Literal["exact", "contains", "starts_with", "keyword_set", "any"] = "contains"
    response: str = Field(default="", max_length=1000)
    priority: int = Field(default=0, ge=0, le=1000)
    cooldown_seconds: int = Field(default=60, ge=0, le=86400)
    enabled: bool = True
    trigger_type: Literal["message.keyword", "instagram.comment"] = "message.keyword"
    status: Literal["DRAFT", "ACTIVE", "PAUSED", "ERROR"] | None = None
    product_id: str | None = None
    scope: Literal["ANY_CONNECTED_MEDIA", "SPECIFIC_MEDIA", "PRODUCT_MEDIA"] = "ANY_CONNECTED_MEDIA"
    media_ids: list[str] = Field(default_factory=list, max_length=100)
    flow: FlowInput | None = None

    @model_validator(mode="after")
    def valid_flow(self):
        if not self.flow and self.cooldown_seconds < 2:
            raise ValueError("legacy_cooldown_minimum")
        if self.match_mode != "any" and not self.keywords:
            raise ValueError("keywords_required")
        if not self.flow and (not self.response or self.trigger_type != "message.keyword"):
            raise ValueError("flow_required")
        if self.scope == "SPECIFIC_MEDIA" and not self.media_ids:
            raise ValueError("media_required")
        if self.scope == "PRODUCT_MEDIA" and not self.product_id:
            raise ValueError("product_required")
        return self

    @field_validator("keywords")
    @classmethod
    def valid_keywords(cls, value):
        if any(not k.strip() or len(k) > 120 for k in value):
            raise ValueError("invalid_keywords")
        return [k.strip() for k in value]


def rule_values(data, db, ws):
    account = owned(db, Account, data.account_id, ws.id)
    if not account.active:
        raise HTTPException(400, "account_inactive")
    if data.product_id:
        owned(db, Product, data.product_id, ws.id)
    for identity in data.media_ids:
        media = owned(db, InstagramMedia, identity, ws.id)
        if media.account_id != account.id:
            raise HTTPException(422, "media_account_mismatch")
    status = data.status or ("ACTIVE" if data.enabled else "PAUSED")
    if status == "ACTIVE" and account.provider == "instagram_mock" and not settings().mock_mode:
        raise HTTPException(422, "sample_account_dry_run_only")
    values = data.model_dump(mode="json")
    values.update(status=status, enabled=status == "ACTIVE", flow=values["flow"] or {})
    return values


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
    row = Automation(workspace_id=ws.id, **rule_values(data, db, ws))
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
    account = db.get(Account, row.account_id)
    if data.enabled and (
        not account.active or (account.provider == "instagram_mock" and not settings().mock_mode)
    ):
        raise HTTPException(422, "account_cannot_activate")
    row.enabled = data.enabled
    row.status = "ACTIVE" if data.enabled else "PAUSED"
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
    for key, value in rule_values(data, db, ws).items():
        setattr(row, key, value)
    audit(db, user.id, "automation.edited", row.id)
    db.commit()
    return serialize(row, RULE_FIELDS)


@router.post("/automations/{identity}/dry-run")
def dry_run(
    identity: str, data: CommentInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from nexa.flows import event_message, queue_flow

    ws = workspace(db, user)
    row = owned(db, Automation, identity, ws.id)
    account = owned(db, Account, data.account_id, ws.id)
    db.refresh(account, with_for_update=True)
    if row.account_id != account.id or not row.flow:
        raise HTTPException(422, "invalid_flow_account")
    media = owned(db, InstagramMedia, data.media_id, ws.id)
    if media.account_id != account.id:
        raise HTTPException(422, "media_account_mismatch")
    rate_limit("dryrun:" + user.id, 30, 60)
    key = f"dry:{row.id}:{data.event_id}"
    existing = db.scalar(select(Message).where(Message.event_key == key))
    if existing:
        execution = db.scalar(
            select(Execution).where(Execution.message_id == existing.id, Execution.automation_id == row.id)
        )
        return {"execution_id": execution.id, "duplicate": True, "dry_run": True}
    payload = data.model_dump(mode="json")
    payload["media_external_id"] = media.external_id
    incoming, conversation = event_message(db, account, key, payload, True)
    execution = queue_flow(db, row, incoming, conversation, account, payload, dry_run=True, force_report=True)
    db.commit()
    return {"execution_id": execution.id, "duplicate": False, "dry_run": True}


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
    rows = db.execute(
        select(Execution, Automation.name, Product.name, InstagramMedia.caption)
        .join(Automation, Automation.id == Execution.automation_id)
        .outerjoin(Product, Product.id == Execution.product_id)
        .outerjoin(InstagramMedia, InstagramMedia.id == Execution.media_id)
        .where(Execution.workspace_id == workspace(db, user).id)
        .order_by(Execution.created_at.desc())
        .offset(offset)
        .limit(100)
    ).all()
    identities = [item[0].id for item in rows]
    actions = {identity: [] for identity in identities}
    if identities:
        for action in db.scalars(
            select(ActionExecution)
            .where(ActionExecution.execution_id.in_(identities))
            .order_by(ActionExecution.execution_id, ActionExecution.position)
        ):
            actions[action.execution_id].append(action.kind)
    result = []
    for execution, automation_name, product_name, media_caption in rows:
        item = serialize(
            execution,
            "id automation_id product_id media_id trigger event_id dry_run status detail created_at",
        )
        item.update(
            automation_name=automation_name,
            product_name=product_name,
            media_caption=media_caption,
            actions=actions[execution.id],
        )
        result.append(item)
    return result


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
