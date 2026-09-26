import json
import logging
import time
from datetime import timedelta

from redis import Redis
from sqlalchemy import select, update

from nexa.automation import deliver, ingest
from nexa.config import settings
from nexa.db import SessionLocal, utcnow
from nexa.flows import run_flow
from nexa.models import ActionExecution, Execution, Job, Message, Notification, TelegramLink, User
from nexa.security import decrypt
from nexa.telegram import handle_update

log = logging.getLogger("nexa.worker")


def deliver_notification(db, job, channel: str):
    notification = db.get(Notification, job.payload["notification_id"])
    if not notification:
        return
    user = db.get(User, notification.user_id)
    if not user or not user.active:
        notification.status = "failed"
        return
    if channel == "email":
        from nexa.email_service import send_email

        send_email(user.email, notification.title, notification.body)
    else:
        link = db.scalar(select(TelegramLink).where(TelegramLink.user_id == user.id))
        if not link:
            notification.status = "failed"
            return
        from nexa.telegram import bot_call

        bot_call("sendMessage", {"chat_id": link.telegram_id, "text": f"{notification.title}\n\n{notification.body}"})
    notification.status = "sent"


def recover_stale(db):
    cutoff = utcnow() - timedelta(minutes=5)
    jobs = db.scalars(select(Job).where(Job.status == "running", Job.locked_at < cutoff).with_for_update())
    for job in jobs:
        if job.kind == "flow":
            execution = db.get(Execution, job.payload["execution_id"])
            sending = db.scalar(
                select(ActionExecution).where(
                    ActionExecution.execution_id == execution.id, ActionExecution.status == "sending"
                )
            )
            if sending:
                sending.status = execution.status = job.status = "unknown"
                execution.detail = "delivery_unknown_manual_review"
                db.execute(
                    update(Message).where(Message.event_key == "flow:" + sending.id).values(status="unknown")
                )
            else:
                job.status = "pending"
        elif job.kind in {"send", "telegram"}:
            job.status = "unknown"
            if job.kind == "send":
                db.execute(
                    update(Message)
                    .where(Message.id == job.payload["message_id"], Message.status.in_(["queued", "sending"]))
                    .values(status="unknown")
                )
                db.execute(
                    update(Execution)
                    .where(
                        Execution.id == job.payload["execution_id"],
                        Execution.status.in_(["queued", "sending"]),
                    )
                    .values(status="unknown")
                )
        else:
            job.status = "pending"
    db.commit()


def run_one() -> bool:
    with SessionLocal() as db:
        job = db.scalar(
            select(Job)
            .where(Job.status == "pending", Job.available_at <= utcnow())
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job.status, job.locked_at, job.attempts = "running", utcnow(), job.attempts + 1
        db.commit()
        try:
            if job.kind == "incoming":
                ingest(db, job)
            elif job.kind == "send":
                deliver(db, job)
            elif job.kind == "telegram":
                handle_update(db, json.loads(decrypt(job.payload["encrypted"])))
            elif job.kind == "notification_email":
                deliver_notification(db, job, "email")
            elif job.kind == "notification_telegram":
                deliver_notification(db, job, "telegram")
            elif job.kind == "flow":
                run_flow(db, job)
            else:
                raise ValueError("unsupported_job")
            if job.status == "running":
                job.status = "complete"
            # Linking tokens and raw webhook bodies need not survive successful processing.
            if job.kind == "telegram":
                job.payload = {}
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job.id)
            job.error = type(exc).__name__
            if job.kind.startswith("notification_"):
                notification = db.get(Notification, job.payload.get("notification_id"))
                if notification:
                    notification.status = "failed"
            job.status = (
                "unknown"
                if job.kind in {"send", "telegram", "flow"} or job.kind.startswith("notification_")
                else ("failed" if job.attempts >= 5 else "pending")
            )
            job.available_at = utcnow() + timedelta(seconds=2**job.attempts)
            if job.kind == "send":
                db.execute(
                    update(Message)
                    .where(Message.id == job.payload["message_id"], Message.status.in_(["queued", "sending"]))
                    .values(status="unknown")
                )
            if job.kind == "flow":
                execution = db.get(Execution, job.payload["execution_id"])
                execution.status, execution.detail = "unknown", "execution_interrupted_manual_review"
                for action in db.scalars(
                    select(ActionExecution).where(
                        ActionExecution.execution_id == execution.id, ActionExecution.status == "sending"
                    )
                ):
                    action.status = "unknown"
                    db.execute(
                        update(Message)
                        .where(Message.event_key == "flow:" + action.id)
                        .values(status="unknown")
                    )
            if job.kind == "send":
                db.execute(
                    update(Execution)
                    .where(
                        Execution.id == job.payload["execution_id"],
                        Execution.status.in_(["queued", "sending"]),
                    )
                    .values(status="unknown")
                )
            db.commit()
            log.error(json.dumps({"event": "job_failed", "job": job.id, "error_type": type(exc).__name__}))
        return True


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    client = Redis.from_url(settings().redis_url, socket_timeout=3)
    while True:
        try:
            client.set("nexa:worker:heartbeat", str(time.time()), ex=30)
            with SessionLocal() as db:
                recover_stale(db)
            if not run_one():
                time.sleep(1)
        except Exception as exc:
            log.error(json.dumps({"event": "worker_unavailable", "error_type": type(exc).__name__}))
            time.sleep(5)


if __name__ == "__main__":
    main()
