"""Versioned actions on the existing durable queue, with conservative delivery recovery."""

from datetime import datetime, timedelta

from sqlalchemy import select

from nexa.commerce_schema import aware
from nexa.config import settings
from nexa.db import now_utc, utcnow
from nexa.models import (
    Account,
    ActionExecution,
    Automation,
    Conversation,
    Execution,
    InstagramMedia,
    Job,
    Lead,
    Message,
    Product,
    User,
    Workspace,
)
from nexa.pricing import calculate
from nexa.providers import DeliveryRejected, DeliveryUnknown, InstagramProvider, RateLimited, provider
from nexa.templates import render

SENDS = {"SEND_DM", "SEND_PRODUCT", "SEND_PRICE"}


def trigger_matches(rule, text, media):
    from nexa.automation import matches

    if rule.scope == "SPECIFIC_MEDIA" and (not media or media.id not in rule.media_ids):
        return False
    if rule.scope == "PRODUCT_MEDIA" and (not media or media.product_id != rule.product_id):
        return False
    if rule.match_mode == "any":
        return True
    return matches(text, rule.keywords, rule.match_mode)


def event_message(db, account, key, data, dry_run=False):
    sender = ("dry:" if dry_run else "") + data["sender"]
    conversation = db.scalar(
        select(Conversation).where(Conversation.account_id == account.id, Conversation.sender_id == sender)
    )
    if not conversation:
        conversation = Conversation(
            workspace_id=account.workspace_id, account_id=account.id, sender_id=sender
        )
        db.add(conversation)
        db.flush()
    incoming = Message(
        workspace_id=account.workspace_id,
        conversation_id=conversation.id,
        event_key=key,
        direction="in",
        text=data["text"],
        status="simulated" if dry_run else "received",
    )
    db.add(incoming)
    db.flush()
    return incoming, conversation


def queue_flow(db, rule, incoming, conversation, account, data, *, dry_run=False, force_report=False):
    media = db.scalar(
        select(InstagramMedia).where(
            InstagramMedia.account_id == account.id,
            InstagramMedia.external_id == data.get("media_external_id", ""),
        )
    )
    matched = trigger_matches(rule, incoming.text, media)
    if not matched and not force_report:
        return None
    product_id = rule.product_id or (media.product_id if media else None)
    product = db.get(Product, product_id) if product_id else None
    recent = db.scalar(
        select(Execution.id)
        .where(
            Execution.conversation_id == conversation.id,
            Execution.product_id == product_id if product_id else Execution.automation_id == rule.id,
            Execution.dry_run == dry_run,
            Execution.status.in_(
                ["queued", "running", "waiting", "sending", "sent", "unknown", "complete", "simulated"]
            ),
            Execution.created_at > utcnow() - timedelta(seconds=rule.cooldown_seconds),
        )
        .limit(1)
    )
    status, detail = "queued", ""
    if not matched:
        status, detail = "skipped", "trigger_not_matched"
    elif product and (product.status != "ACTIVE" or product.availability == "OUT_OF_STOCK"):
        status, detail = "skipped", "product_inactive"
    elif recent:
        status, detail = "cooldown", "customer_product_cooldown"
    execution = Execution(
        workspace_id=account.workspace_id,
        automation_id=rule.id,
        message_id=incoming.id,
        conversation_id=conversation.id,
        product_id=product_id,
        media_id=media.id if media else None,
        trigger=rule.trigger_type,
        event_id=data.get("event_id"),
        dry_run=dry_run,
        status=status,
        detail=detail,
        started_at=now_utc(),
        context={
            "sender": data["sender"],
            "display_name": data.get("display_name", ""),
            "text": incoming.text,
            "media_external_id": data.get("media_external_id", ""),
            "occurred_at": data.get("occurred_at"),
            "sample_rate": data.get("sample_rate") if dry_run else None,
            "matched": matched,
        },
    )
    db.add(execution)
    db.flush()
    for position, action in enumerate(rule.flow["actions"]):
        db.add(
            ActionExecution(
                execution_id=execution.id,
                position=position,
                kind=action["type"],
                config=action,
                status="pending" if status == "queued" else "skipped",
            )
        )
    db.flush()
    if status == "queued":
        if dry_run:
            run_flow(db, execution=execution)
        else:
            db.add(Job(key="flow:" + execution.id, kind="flow", payload={"execution_id": execution.id}))
    else:
        execution.completed_at = now_utc()
    return execution


def ingest_comment(db, job):
    data = job.payload
    account = db.scalar(select(Account).where(Account.id == data["account_id"]).with_for_update())
    if (
        not account
        or not account.active
        or not db.get(User, db.get(Workspace, account.workspace_id).owner_id).active
    ):
        return
    if db.scalar(select(Message.id).where(Message.event_key == job.key)):
        return
    incoming, conversation = event_message(db, account, job.key, data)
    rules = db.scalars(
        select(Automation)
        .where(
            Automation.account_id == account.id,
            Automation.enabled.is_(True),
            Automation.status == "ACTIVE",
            Automation.trigger_type == "instagram.comment",
        )
        .order_by(Automation.priority.desc(), Automation.created_at, Automation.id)
    )
    for rule in rules:
        if rule.flow and queue_flow(db, rule, incoming, conversation, account, data):
            break


def ensure_lead(db, account, execution):
    context = execution.context
    lead = db.scalar(select(Lead).where(Lead.account_id == account.id, Lead.external_id == context["sender"]))
    if not lead:
        lead = Lead(
            workspace_id=account.workspace_id,
            account_id=account.id,
            provider=account.provider,
            external_id=context["sender"],
            display_name=context.get("display_name", ""),
            source=execution.trigger,
            tags=[],
            notes=[],
        )
        db.add(lead)
    lead.last_interaction = now_utc()
    if context.get("display_name"):
        lead.display_name = context["display_name"][:120]
    db.flush()
    return lead


def template_context(db, execution, product):
    context = execution.context
    values = {
        "customer": {"name": context.get("display_name") or context["sender"]},
        "comment": {"text": context["text"]},
        "instagram": {"username": context.get("display_name", "")},
    }
    pricing = None
    if product:
        pricing = calculate(
            db, product, sample_rate=context.get("sample_rate") if execution.dry_run else None
        )
        values["product"] = {
            "name": product.name,
            "description": product.description,
            "base_price": str(product.base_price),
            "base_currency": product.base_currency,
            "price": pricing["formatted_price"],
            "currency": {"USD": "دلار", "EUR": "یورو", "AED": "درهم", "IRR": "ریال", "TOMAN": "تومان"}[
                product.output_currency
            ],
            "converted_price": pricing["converted_price"],
            "url": product.url,
        }
        values["exchange"] = {"rate": pricing["rate"], "updated_at": pricing["updated_at"]}
    return values, pricing


def check_window(account, execution, conversation):
    if execution.trigger == "instagram.comment":
        occurred = execution.context.get("occurred_at")
        if execution.dry_run:
            created = datetime.fromisoformat(occurred) if occurred else now_utc()
        else:
            # Notification entry.time is not the original comment creation time.
            data = InstagramProvider().comment(account, execution.event_id)
            if str(data.get("media", {}).get("id", "")) != execution.context["media_external_id"]:
                raise DeliveryRejected("comment_media_mismatch")
            if str(data.get("from", {}).get("id", "")) != execution.context["sender"]:
                raise DeliveryRejected("comment_sender_mismatch")
            if data.get("media", {}).get("media_product_type") not in {"FEED", "REELS"}:
                raise DeliveryRejected("unsupported_media_surface")
            created = data["occurred_at"]
        age = now_utc() - aware(created)
        if age > timedelta(days=7) or age < timedelta(minutes=-5):
            raise DeliveryRejected("private_reply_window_expired")
    elif not execution.dry_run and account.provider == "instagram":
        if not conversation.last_inbound_at or now_utc() - aware(conversation.last_inbound_at) >= timedelta(
            hours=24
        ):
            raise DeliveryRejected("messaging_window_expired")


def run_flow(db, job=None, *, execution=None):
    execution = execution or db.get(Execution, job.payload["execution_id"])
    if execution.status not in {"queued", "running", "waiting"}:
        return
    rule = db.get(Automation, execution.automation_id)
    # Serialize lead/cooldown updates and sends for this account across workers.
    conversation = db.get(Conversation, execution.conversation_id)
    account = db.scalar(select(Account).where(Account.id == conversation.account_id).with_for_update())
    owner = db.get(User, db.get(Workspace, account.workspace_id).owner_id)
    product = db.get(Product, execution.product_id) if execution.product_id else None
    if (
        not account.active
        or not owner.active
        or rule.account_id != account.id
        or (not execution.dry_run and account.provider == "instagram_mock" and not settings().mock_mode)
        or (not execution.dry_run and (not rule.enabled or rule.status != "ACTIVE"))
        or (product and (product.status != "ACTIVE" or product.availability == "OUT_OF_STOCK"))
    ):
        execution.status, execution.detail, execution.completed_at = "cancelled", "source_inactive", now_utc()
        db.commit()
        return
    execution.status = "running"
    actions = list(
        db.scalars(
            select(ActionExecution)
            .where(ActionExecution.execution_id == execution.id)
            .order_by(ActionExecution.position)
        )
    )
    for action in actions:
        if action.status in {"complete", "sent", "simulated"}:
            continue
        if action.status == "sending":
            execution.status = action.status = "unknown"
            execution.detail = "delivery_unknown_manual_review"
            break
        action.started_at = action.started_at or now_utc()
        try:
            if action.kind == "DELAY":
                action.status, action.result, action.completed_at = (
                    "complete",
                    {"seconds": action.config["seconds"], "simulated": execution.dry_run},
                    now_utc(),
                )
                if not execution.dry_run and action.config["seconds"]:
                    execution.status, job.status = "waiting", "pending"
                    job.available_at = utcnow() + timedelta(seconds=action.config["seconds"])
                    db.commit()
                    return
            elif action.kind in SENDS:
                db.refresh(rule)
                db.refresh(account)
                db.refresh(owner)
                if product:
                    db.refresh(product)
                if (
                    not account.active
                    or not owner.active
                    or rule.account_id != account.id
                    or (not execution.dry_run and (not rule.enabled or rule.status != "ACTIVE"))
                    or (product and (product.status != "ACTIVE" or product.availability == "OUT_OF_STOCK"))
                ):
                    raise DeliveryRejected("source_inactive")
                check_window(account, execution, conversation)
                values, pricing = template_context(db, execution, product)
                if action.kind in {"SEND_PRODUCT", "SEND_PRICE"} and not product:
                    raise ValueError("product_required")
                text = render(action.config["template"], values)
                action.result = {"rendered_text": text, "pricing": pricing, "simulated": execution.dry_run}
                if execution.dry_run:
                    action.status = "simulated"
                else:
                    outgoing = db.scalar(select(Message).where(Message.event_key == "flow:" + action.id))
                    if not outgoing:
                        outgoing = Message(
                            workspace_id=execution.workspace_id,
                            conversation_id=conversation.id,
                            direction="out",
                            event_key="flow:" + action.id,
                            text=text,
                            status="queued",
                        )
                        db.add(outgoing)
                    action.attempts += 1
                    action.status = outgoing.status = "sending"
                    # A committed marker prevents retries after uncertain network delivery/crash.
                    db.commit()
                    try:
                        adapter = provider(account.provider)
                        receipt = (
                            adapter.private_reply(account, execution.event_id, text, action.id)
                            if execution.trigger == "instagram.comment"
                            else adapter.send(account, execution.context["sender"], text, action.id)
                        )
                    except RateLimited:
                        outgoing.status = "queued"
                        raise
                    except DeliveryRejected:
                        outgoing.status = "failed"
                        raise
                    except DeliveryUnknown:
                        outgoing.status = "unknown"
                        raise
                    outgoing.status = action.status = "sent"
                    outgoing.provider_message_id = receipt.message_id
                    action.result = {**action.result, "provider_message_id": receipt.message_id}
            else:
                if execution.dry_run:
                    action.status, action.result = (
                        "simulated",
                        {"value": action.config.get("value", ""), "simulated": True},
                    )
                else:
                    lead = ensure_lead(db, account, execution)
                    if action.kind == "ADD_TAG":
                        lead.tags = list(dict.fromkeys(lead.tags + [action.config["value"]]))[-30:]
                    elif action.kind == "INTERNAL_NOTE":
                        lead.notes = (
                            lead.notes
                            + [
                                {
                                    "text": action.config["value"],
                                    "at": now_utc().isoformat(),
                                    "execution_id": execution.id,
                                }
                            ]
                        )[-100:]
                    action.status, action.result = "complete", {"lead_id": lead.id}
            action.completed_at = now_utc()
            # Commit after each completed action; resume never repeats completed side effects.
            db.commit()
        except RateLimited as exc:
            # Reads can also be throttled; count every explicit rate-limit response.
            if action.status != "sending":
                action.attempts += 1
            if job and action.attempts < 5:
                action.status, execution.status, job.status = "pending", "waiting", "pending"
                job.available_at = utcnow() + timedelta(
                    seconds=max(exc.retry_after, min(3600, 30 * 2**action.attempts))
                )
                action.result = {
                    **action.result,
                    "error": "rate_limited",
                    "retry_at": aware(job.available_at).isoformat(),
                }
                db.commit()
                return
            action.status = execution.status = "failed"
            execution.detail = "rate_limit_exhausted"
            break
        except DeliveryUnknown:
            action.status = execution.status = "unknown"
            execution.detail = "delivery_unknown_manual_review"
            break
        except (DeliveryRejected, ValueError) as exc:
            action.status = execution.status = "failed"
            execution.detail = str(exc)[:128]
            action.result = {**action.result, "error": execution.detail}
            if not execution.dry_run and execution.detail in {
                "reconnect_required",
                "permission_required",
                "credentials_missing",
            }:
                rule.status, rule.enabled = "ERROR", False
            break
    if execution.status == "running":
        execution.status = "simulated" if execution.dry_run else "complete"
    execution.completed_at = now_utc()
    for action in actions:
        if action.status in {"failed", "unknown"}:
            action.completed_at = now_utc()
        if action.status == "pending":
            action.status = "skipped"
    db.commit()
