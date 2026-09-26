import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from redis import Redis
from redis.exceptions import RedisError
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


def _set_session(db, user: User, response: Response, action: str):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        Session(
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=utcnow() + timedelta(hours=settings().session_hours),
        )
    )
    audit(db, user.id, action)
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
    return _set_session(db, user, response, "auth.login")


def _google_redirect(status: str) -> RedirectResponse:
    return RedirectResponse(url=f"/?google={status}&auth=1", status_code=303)


def _google_callback_redirect(status: str, request: Request) -> RedirectResponse:
    redirect = _google_redirect(status)
    if request.cookies.get("nexa_google_state"):
        redirect.delete_cookie("nexa_google_state", path="/")
    return redirect


def _google_state_key(state: str) -> str:
    return "oauth:google:" + digest(state)


def _save_google_state(state: str) -> None:
    client = Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.set(_google_state_key(state), "1", ex=600, nx=True)
    except RedisError:
        raise HTTPException(503, "temporarily_unavailable") from None
    finally:
        client.close()


def _consume_google_state(state: str) -> bool:
    client = Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        key = _google_state_key(state)
        value = client.get(key)
        if value:
            client.delete(key)
        return bool(value)
    except RedisError:
        raise HTTPException(503, "temporarily_unavailable") from None
    finally:
        client.close()


def _google_username(db: DBSession, email: str, google_sub: str) -> str:
    local = re.sub(r"[^a-zA-Z0-9_]", "_", email.split("@", 1)[0]).strip("_").lower() or "google_user"
    suffix = re.sub(r"[^a-zA-Z0-9]", "", google_sub)[-8:].lower() or secrets.token_hex(4)
    base = f"{local[:48]}_{suffix}"[:64]
    candidate = base
    while db.scalar(select(User).where(User.username == candidate)):
        candidate = f"{base[:55]}_{secrets.token_hex(4)}"[:64]
    return candidate


@router.get("/google/start")
def google_start(request: Request):
    if not settings().google_login_enabled:
        return _google_redirect("unavailable")
    rate_limit("google-start:" + request.client.host, 10, 900)
    state = secrets.token_urlsafe(32)
    try:
        _save_google_state(state)
    except HTTPException:
        return _google_redirect("failed")
    params = {
        "client_id": settings().google_client_id,
        "redirect_uri": settings().public_urls["google_callback"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    redirect = RedirectResponse(
        url="https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=303
    )
    redirect.set_cookie(
        "nexa_google_state",
        state,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        path="/",
        max_age=600,
    )
    return redirect


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: DBSession = Depends(get_db),
):
    if not settings().google_login_enabled:
        return _google_callback_redirect("unavailable", request)
    if error == "access_denied":
        return _google_callback_redirect("cancelled", request)
    if not code or not state:
        return _google_callback_redirect("failed", request)
    try:
        saved_state = request.cookies.get("nexa_google_state")
        if not saved_state or not secrets.compare_digest(saved_state, state):
            return _google_callback_redirect("failed", request)
        if not _consume_google_state(state):
            return _google_callback_redirect("failed", request)
        with httpx.Client(timeout=15.0) as client:
            token_response = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings().google_client_id,
                    "client_secret": settings().google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings().public_urls["google_callback"],
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("missing_access_token")
            profile_response = client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": "Bearer " + access_token},
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
        google_sub = profile.get("sub")
        email = profile.get("email")
        verified = profile.get("email_verified") is True or str(profile.get("email_verified")).lower() == "true"
        if not isinstance(google_sub, str) or not google_sub or not isinstance(email, str) or not verified:
            raise ValueError("invalid_google_profile")
        email = email.strip().lower()
        if "@" not in email or len(email) > 254:
            raise ValueError("invalid_google_email")
        action = "auth.google_login"
        user = db.scalar(select(User).where(User.google_sub == google_sub))
        if user is None:
            user = db.scalar(select(User).where(User.email == email))
            if user is not None:
                if user.google_sub and user.google_sub != google_sub:
                    raise ValueError("google_identity_conflict")
                user.google_sub = google_sub
                action = "auth.google_linked"
            else:
                if not settings().registration_enabled:
                    return _google_callback_redirect("unavailable", request)
                user = User(
                    username=_google_username(db, email, google_sub),
                    email=email,
                    google_sub=google_sub,
                    password_hash=hasher.hash(secrets.token_urlsafe(48)),
                    role="USER",
                )
                db.add(user)
                db.flush()
                db.add(Workspace(owner_id=user.id, name=user.username))
                action = "auth.google_register"
        elif not user.active:
            return _google_callback_redirect("failed", request)
        redirect = _google_callback_redirect("success", request)
        _set_session(db, user, redirect, action)
        return redirect
    except (httpx.HTTPError, KeyError, TypeError, ValueError, IntegrityError):
        db.rollback()
        return _google_callback_redirect("failed", request)


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
