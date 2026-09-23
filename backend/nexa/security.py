import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, MultiFernet
from fastapi import Depends, HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from nexa.config import settings
from nexa.db import get_db, utcnow
from nexa.models import Audit, OneTimeToken, Session, User, Workspace

hasher = PasswordHasher()
PERMISSIONS = {"users.read": {"ADMIN", "SUPER_ADMIN"}, "system.manage": {"SUPER_ADMIN"}}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def validate_password(value: str) -> str:
    if len(value) < 12 or len(value) > 256 or len(set(value)) < 6:
        raise ValueError("password_strength")
    return value


def verify_password(value: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, value)
    except (VerificationError, InvalidHashError):
        return False


def encrypt(value: str) -> str:
    return (
        MultiFernet([Fernet(k.strip().encode()) for k in settings().encryption_keys.split(",")])
        .encrypt(value.encode())
        .decode()
    )


def decrypt(value: str) -> str:
    return (
        MultiFernet([Fernet(k.strip().encode()) for k in settings().encryption_keys.split(",")])
        .decrypt(value.encode())
        .decode()
    )


def rate_limit(key: str, limit: int, seconds: int):
    client = Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        count = client.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
            1,
            "limit:" + digest(key),
            seconds,
        )
        if count > limit:
            raise HTTPException(429, "rate_limited", headers={"Retry-After": str(seconds)})
    except RedisError:
        raise HTTPException(503, "temporarily_unavailable") from None
    finally:
        client.close()


def audit(db: DBSession, user_id: str | None, action: str, target: str = "", **detail):
    db.add(Audit(user_id=user_id, action=action, target=target, detail=detail))


def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    session = db.scalar(
        select(Session).where(
            Session.token_hash == digest(request.cookies.get("nexa_session", "")),
            Session.expires_at > utcnow(),
        )
    )
    user = db.get(User, session.user_id) if session else None
    if not user or not user.active:
        raise HTTPException(401, "authentication_required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not secrets.compare_digest(session.csrf_hash, digest(request.headers.get("X-CSRF-Token", ""))):
            raise HTTPException(403, "csrf_invalid")
    request.state.session = session
    return user


def require(permission: str):
    def dependency(user: User = Depends(current_user)):
        if user.role not in PERMISSIONS[permission]:
            raise HTTPException(403, "forbidden")
        return user

    return dependency


def workspace(db: DBSession, user: User) -> Workspace:
    return db.scalar(select(Workspace).where(Workspace.owner_id == user.id))


def owned(db: DBSession, model, identity: str, workspace_id: str):
    item = db.scalar(select(model).where(model.id == identity, model.workspace_id == workspace_id))
    if not item:
        raise HTTPException(404, "not_found")
    return item


def issue_token(db: DBSession, user_id: str, purpose: str, minutes: int = 10) -> str:
    for old in db.scalars(
        select(OneTimeToken).where(
            OneTimeToken.user_id == user_id,
            OneTimeToken.purpose == purpose,
            OneTimeToken.consumed_at.is_(None),
        )
    ):
        old.consumed_at = utcnow()
    token = secrets.token_urlsafe(32)
    db.add(
        OneTimeToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=digest(token),
            expires_at=utcnow() + timedelta(minutes=minutes),
        )
    )
    return token


def consume_token(db: DBSession, token: str, purpose: str) -> OneTimeToken:
    row = db.scalar(
        select(OneTimeToken)
        .where(
            OneTimeToken.token_hash == digest(token),
            OneTimeToken.purpose == purpose,
            OneTimeToken.consumed_at.is_(None),
            OneTimeToken.expires_at > utcnow(),
        )
        .with_for_update()
    )
    if not row:
        raise ValueError("invalid_or_expired_token")
    row.consumed_at = utcnow()
    db.flush()
    return row
