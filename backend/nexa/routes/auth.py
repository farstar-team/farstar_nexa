import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from nexa.config import settings
from nexa.db import get_db, utcnow
from nexa.models import Session, User, Workspace
from nexa.security import (
    audit,
    consume_token,
    current_user,
    digest,
    hasher,
    issue_token,
    rate_limit,
    validate_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
# Equal-cost verification when a username does not exist.
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


class Register(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,64}$")
    email: EmailStr
    password: str = Field(max_length=256)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        return validate_password(value)


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


def user_dict(user: User):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "timezone": user.timezone,
        "created_at": user.created_at.isoformat() + "Z",
    }


def create_user(db, data: Register, role="USER"):
    user = User(
        username=data.username.lower(),
        email=str(data.email).lower(),
        password_hash=hasher.hash(data.password),
        role=role,
    )
    db.add(user)
    db.flush()
    db.add(Workspace(owner_id=user.id, name=user.username))
    return user


@router.post("/register", status_code=201)
def register(data: Register, request: Request, db: DBSession = Depends(get_db)):
    if not settings().registration_enabled:
        raise HTTPException(403, "registration_disabled")
    rate_limit("register:" + request.client.host, 5, 3600)
    try:
        user = create_user(db, data)
        audit(db, user.id, "auth.register")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "account_exists") from None
    return user_dict(user)


@router.post("/login")
def login(data: Login, request: Request, response: Response, db: DBSession = Depends(get_db)):
    rate_limit("login-ip:" + request.client.host, 30, 900)
    rate_limit("login-user:" + data.username.lower(), 10, 900)
    user = db.scalar(select(User).where(User.username == data.username.lower()))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not valid or not user or not user.active:
        raise HTTPException(401, "invalid_credentials")
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        Session(
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=utcnow() + timedelta(hours=settings().session_hours),
        )
    )
    audit(db, user.id, "auth.login")
    db.commit()
    opts = {
        "secure": settings().cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": settings().session_hours * 3600,
    }
    response.set_cookie("nexa_session", token, httponly=True, **opts)
    response.set_cookie("nexa_csrf", csrf, httponly=False, **opts)
    return user_dict(user)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


@router.post("/logout")
def logout(
    request: Request, response: Response, user: User = Depends(current_user), db: DBSession = Depends(get_db)
):
    db.delete(request.state.session)
    audit(db, user.id, "auth.logout")
    db.commit()
    response.delete_cookie("nexa_session", path="/")
    response.delete_cookie("nexa_csrf", path="/")
    return {"ok": True}


class Profile(BaseModel):
    email: EmailStr
    timezone: str = Field(max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("invalid_timezone") from None
        return value


@router.patch("/profile")
def profile(data: Profile, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    user.email, user.timezone = str(data.email).lower(), data.timezone
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "account_exists") from None
    return user_dict(user)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value):
        return validate_password(value)


@router.post("/password")
def change_password(
    data: PasswordChange, user: User = Depends(current_user), db: DBSession = Depends(get_db)
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "invalid_credentials")
    user.password_hash = hasher.hash(data.new_password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user.id, "auth.password_changed")
    db.commit()
    return {"ok": True}


class ResetPassword(BaseModel):
    token: str = Field(max_length=128)
    password: str = Field(max_length=256)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        return validate_password(value)


class ResetRequest(BaseModel):
    email: EmailStr


@router.post("/request-reset")
def request_reset(data: ResetRequest, request: Request, db: DBSession = Depends(get_db)):
    rate_limit("reset-request:" + request.client.host, 10, 900)
    user = db.scalar(select(User).where(User.email == str(data.email).lower(), User.active.is_(True)))
    if user:
        token = issue_token(db, user.id, "password_reset", minutes=30)
        audit(db, user.id, "auth.password_reset_requested")
        db.commit()
        try:
            from nexa.email_service import send_email

            send_email(
                user.email,
                "بازیابی رمز عبور Farstar Nexa",
                f"برای تعیین رمز عبور تازه، این پیوند را باز کنید:\n{settings().base_url}/?recovery={token}",
            )
        except Exception:
            # Keep the response generic and never reveal account existence or SMTP details.
            pass
    return {"ok": True}


@router.post("/reset-password")
def reset_password(data: ResetPassword, request: Request, db: DBSession = Depends(get_db)):
    rate_limit("reset:" + request.client.host, 10, 900)
    try:
        row = consume_token(db, data.token, "password_reset")
    except ValueError:
        raise HTTPException(400, "invalid_or_expired_token") from None
    user = db.get(User, row.user_id)
    user.password_hash = hasher.hash(data.password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user.id, "auth.password_reset")
    db.commit()
    return {"ok": True}
