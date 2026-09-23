from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexa.db import get_db
from nexa.integration_config import integration_settings
from nexa.models import Account, User
from nexa.security import audit, consume_token, current_user, encrypt, issue_token, workspace

router = APIRouter(prefix="/api/instagram", tags=["instagram"])


@router.post("/authorize")
def authorize(user: User = Depends(current_user), db: Session = Depends(get_db)):
    config = integration_settings()
    if not config.meta_app_id or not config.meta_app_secret or not config.base_url.startswith("https://"):
        raise HTTPException(503, "meta_not_configured")
    state = issue_token(db, user.id, "instagram_oauth")
    db.commit()
    params = {
        "client_id": config.meta_app_id,
        "redirect_uri": config.base_url + "/api/instagram/callback",
        "response_type": "code",
        "scope": "instagram_business_basic,instagram_business_manage_messages",
        "state": state,
        "enable_fb_login": "0",
        "force_authentication": "1",
    }
    return {"url": "https://www.instagram.com/oauth/authorize?" + urlencode(params)}


@router.get("/callback")
def callback(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    config = integration_settings()
    try:
        token = consume_token(db, request.query_params.get("state", ""), "instagram_oauth")
        if token.user_id != user.id:
            raise ValueError("wrong_owner")
        db.commit()
        code = request.query_params.get("code", "")
        if not code:
            raise ValueError("authorization_denied")
        with httpx.Client(timeout=20) as client:
            result = client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": config.meta_app_id,
                    "client_secret": config.meta_app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": config.base_url + "/api/instagram/callback",
                    "code": code,
                },
            )
            result.raise_for_status()
            access = result.json()["access_token"]
            extended = client.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": config.meta_app_secret,
                    "access_token": access,
                },
            )
            extended.raise_for_status()
            access = extended.json()["access_token"]
            headers = {"Authorization": "Bearer " + access}
            profile = client.get(
                f"https://graph.instagram.com/{config.meta_api_version}/me",
                params={"fields": "user_id,username"},
                headers=headers,
            )
            profile.raise_for_status()
            identity = str(profile.json()["user_id"])
            ws = workspace(db, user)
            existing = db.scalar(
                select(Account).where(Account.provider == "instagram", Account.external_id == identity)
            )
            if existing and existing.workspace_id != ws.id:
                raise ValueError("account_already_owned")
            subscribed = client.post(
                f"https://graph.instagram.com/{config.meta_api_version}/{identity}/subscribed_apps",
                headers=headers,
                data={"subscribed_fields": "messages"},
            )
            subscribed.raise_for_status()
            if subscribed.json().get("success") is not True:
                raise ValueError("subscription_failed")
            row = existing or Account(workspace_id=ws.id, provider="instagram", external_id=identity)
            row.name, row.credential, row.active = profile.json()["username"], encrypt(access), True
            db.add(row)
            audit(db, user.id, "instagram.connected", identity)
            db.commit()
    except (ValueError, KeyError, httpx.HTTPError, IntegrityError):
        db.rollback()
        audit(db, user.id, "instagram.connection_failed")
        db.commit()
        return RedirectResponse("/?connection=failed", status_code=303)
    return RedirectResponse("/?connection=success", status_code=303)
