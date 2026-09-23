import unicodedata
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexa.db import utcnow
from nexa.models import Account, Automation, Conversation, Execution, Job, Message, User, Workspace
from nexa.providers import DeliveryRejected, DeliveryUnknown, provider


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(str.maketrans("يك", "یک")).casefold().strip()


def matches(text: str, keywords: list[str], mode: str) -> bool:
    text = normalize(text)
    for keyword in keywords:
        keyword = normalize(keyword)
        if not keyword:
            continue
        if mode == "exact" and text == keyword:
            return True
        if mode == "contains" and keyword in text:
            return True
        if mode == "starts_with" and text.startswith(keyword):
            return True
    return False


def ingest(db: Session, job: Job):
    data = job.payload
    account = db.scalar(select(Account).where(Account.id == data["account_id"]).with_for_update())
    if not account or not account.active or data.get("echo"):
        return
    owner = db.get(User, db.get(Workspace, account.workspace_id).owner_id)
    if not owner.active:
        return
    if db.scalar(select(Message.id).where(Message.event_key == job.key)):
        return
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.account_id == account.id, Conversation.sender_id == data["sender"]
        )
    )
    if not conversation:
        conversation = Conversation(
            workspace_id=account.workspace_id, account_id=account.id, sender_id=data["sender"]
        )
        db.add(conversation)
        db.flush()
    incoming = Message(
        workspace_id=account.workspace_id,
        conversation_id=conversation.id,
        event_key=job.key,
        direction="in",
        text=data["text"],
    )
    db.add(incoming)
    db.flush()
    rules = db.scalars(
        select(Automation)
        .where(Automation.account_id == account.id, Automation.enabled.is_(True))
        .order_by(Automation.priority.desc(), Automation.created_at, Automation.id)
    )
    for rule in rules:
        if rule.trigger_type != "message.keyword" or rule.action_type != "message.reply":
            continue
        if not matches(incoming.text, rule.keywords, rule.match_mode):
            continue
        recent = db.scalar(
            select(Execution.id).where(
                Execution.automation_id == rule.id,
                Execution.conversation_id == conversation.id,
                Execution.status.in_(["queued", "sending", "sent", "unknown"]),
                Execution.created_at > utcnow() - timedelta(seconds=max(rule.cooldown_seconds, 2)),
            )
        )
        execution = Execution(
            workspace_id=account.workspace_id,
            automation_id=rule.id,
            conversation_id=conversation.id,
            message_id=incoming.id,
            status="cooldown" if recent else "queued",
        )
        db.add(execution)
        db.flush()
        if not recent:
            outgoing = Message(
                workspace_id=account.workspace_id,
                conversation_id=conversation.id,
                event_key="reply:" + incoming.id,
                direction="out",
                text=rule.response,
                status="queued",
            )
            db.add(outgoing)
            db.flush()
            db.add(
                Job(
                    key="send:" + incoming.id,
                    kind="send",
                    payload={
                        "message_id": outgoing.id,
                        "execution_id": execution.id,
                        "account_id": account.id,
                        "recipient": conversation.sender_id,
                    },
                )
            )
        # Only the highest-priority matching rule can reply to an incoming message.
        break


def deliver(db: Session, job: Job):
    outgoing = db.get(Message, job.payload["message_id"])
    execution = db.get(Execution, job.payload["execution_id"])
    account = db.get(Account, job.payload["account_id"])
    if outgoing.status != "queued":
        return
    owner = db.get(User, db.get(Workspace, account.workspace_id).owner_id)
    if not account.active or not owner.active:
        outgoing.status = execution.status = "cancelled"
        db.commit()
        return
    outgoing.status = execution.status = "sending"
    db.commit()
    try:
        receipt = provider(account.provider).send(account, job.payload["recipient"], outgoing.text, job.key)
        outgoing.provider_message_id = receipt.message_id
        outgoing.status = execution.status = "sent"
    except DeliveryUnknown:
        outgoing.status = execution.status = "unknown"
        execution.detail = "delivery_unknown_manual_review"
    except DeliveryRejected:
        outgoing.status = execution.status = "failed"
        execution.detail = "provider_rejected"
    db.commit()
