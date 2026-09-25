from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexa.commerce_schema import Currency, ProductInput, Rate, StrictInput
from nexa.config import settings
from nexa.db import get_db, now_utc
from nexa.models import (
    Account,
    ActionExecution,
    Automation,
    Execution,
    InstagramMedia,
    Lead,
    Product,
    User,
    WorkspaceRate,
)
from nexa.pricing import PROVIDERS, PricingUnavailable, calculate
from nexa.providers import DeliveryRejected, InstagramProvider
from nexa.routes.workspace import serialize
from nexa.security import audit, current_user, owned, rate_limit, workspace

router = APIRouter(prefix="/api", tags=["commerce"])
PRODUCT_FIELDS = "id name slug description sku status availability base_price base_currency output_currency pricing_mode manual_rate pricing url custom_fields created_at updated_at"
MEDIA_FIELDS = (
    "id account_id external_id product_id caption media_type permalink thumbnail_url published_at synced_at"
)
LEAD_FIELDS = (
    "id account_id provider external_id display_name source tags notes first_interaction last_interaction"
)


def product_values(data):
    values = data.model_dump()
    values["pricing"] = data.pricing.model_dump(mode="json")
    return values


@router.get("/products")
def products(user: User = Depends(current_user), db: Session = Depends(get_db), offset: int = Query(0, ge=0)):
    return [
        serialize(row, PRODUCT_FIELDS)
        for row in db.scalars(
            select(Product)
            .where(Product.workspace_id == workspace(db, user).id)
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(100)
        )
    ]


@router.post("/products/preview")
def preview(data: ProductInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = Product(workspace_id=workspace(db, user).id, **product_values(data))
    try:
        return calculate(db, product)
    except PricingUnavailable as exc:
        raise HTTPException(422, str(exc)) from None


def save_product(db, user, row):
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "product_slug_exists") from None
    audit(db, user.id, "product.saved", row.id)
    db.commit()
    return serialize(row, PRODUCT_FIELDS)


@router.post("/products", status_code=201)
def create_product(data: ProductInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return save_product(db, user, Product(workspace_id=workspace(db, user).id, **product_values(data)))


@router.put("/products/{identity}")
def edit_product(
    identity: str, data: ProductInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = owned(db, Product, identity, workspace(db, user).id)
    for key, value in product_values(data).items():
        setattr(row, key, value)
    return save_product(db, user, row)


@router.delete("/products/{identity}")
def delete_product(identity: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = owned(db, Product, identity, workspace(db, user).id)
    for model in (Automation, InstagramMedia, Execution):
        if db.scalar(select(model.id).where(model.product_id == row.id).limit(1)):
            raise HTTPException(409, "product_in_use_deactivate_instead")
    db.delete(row)
    audit(db, user.id, "product.deleted", identity)
    db.commit()
    return {"ok": True}


class RateInput(StrictInput):
    base_currency: Currency
    quote_currency: Currency
    rate: Rate


@router.get("/exchange-rates")
def rates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(WorkspaceRate).where(WorkspaceRate.workspace_id == workspace(db, user).id))
    return {
        "manual": [serialize(row, "id base_currency quote_currency rate updated_at") for row in rows],
        "provider": PROVIDERS[settings().exchange_provider].health(),
        "attribution_url": "https://www.exchangerate-api.com",
        "attribution": "Rates By Exchange Rate API",
    }


@router.put("/exchange-rates")
def set_rate(data: RateInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace(db, user)
    # Serializes concurrent updates within a workspace, including first insert.
    db.refresh(ws, with_for_update=True)
    row = db.scalar(
        select(WorkspaceRate).where(
            WorkspaceRate.workspace_id == ws.id,
            WorkspaceRate.base_currency == data.base_currency,
            WorkspaceRate.quote_currency == data.quote_currency,
        )
    )
    if not row:
        row = WorkspaceRate(workspace_id=ws.id, **data.model_dump())
        db.add(row)
    row.rate = data.rate
    row.updated_at = now_utc()
    audit(db, user.id, "exchange.manual_updated")
    db.commit()
    return serialize(row, "id base_currency quote_currency rate updated_at")


@router.get("/media")
def media(
    account_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    offset: int = Query(0, ge=0),
):
    owned(db, Account, account_id, workspace(db, user).id)
    return [
        serialize(row, MEDIA_FIELDS)
        for row in db.scalars(
            select(InstagramMedia)
            .where(InstagramMedia.account_id == account_id)
            .order_by(InstagramMedia.published_at.desc(), InstagramMedia.id)
            .offset(offset)
            .limit(100)
        )
    ]


class SyncInput(StrictInput):
    account_id: str
    cursor: str | None = Field(default=None, max_length=2048)


@router.post("/media/sync")
def sync_media(data: SyncInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = owned(db, Account, data.account_id, workspace(db, user).id)
    db.refresh(account, with_for_update=True)
    if not account.active:
        raise HTTPException(400, "account_inactive")
    rate_limit("media:" + account.id, 30, 60)
    if account.provider == "instagram_mock":
        payload = {
            "data": [
                {
                    "id": "sample-post",
                    "caption": "پست نمونه برای تست؛ اتصال واقعی نیست",
                    "media_type": "IMAGE",
                },
                {"id": "sample-reel", "caption": "ریل نمونه برای تست", "media_type": "REELS"},
            ]
        }
    else:
        try:
            payload = InstagramProvider().list_media(account, data.cursor)
        except DeliveryRejected as exc:
            raise HTTPException(422, str(exc)) from None
    items = []
    for item in payload.get("data", [])[:100]:
        external_id = str(item["id"])
        row = db.scalar(
            select(InstagramMedia).where(
                InstagramMedia.account_id == account.id, InstagramMedia.external_id == external_id
            )
        )
        if not row:
            row = InstagramMedia(
                workspace_id=account.workspace_id, account_id=account.id, external_id=external_id
            )
            db.add(row)
        row.caption = str(item.get("caption", ""))[:2200]
        row.media_type = str(item.get("media_product_type") or item.get("media_type", "UNKNOWN"))[:32]
        row.permalink = safe_remote_url(item.get("permalink", ""), ("instagram.com",))
        row.thumbnail_url = safe_remote_url(
            item.get("thumbnail_url") or item.get("media_url", ""), ("cdninstagram.com", "fbcdn.net")
        )
        row.published_at = datetime.fromisoformat(item["timestamp"]) if item.get("timestamp") else None
        row.synced_at = now_utc()
        db.flush()
        items.append(serialize(row, MEDIA_FIELDS))
    db.commit()
    paging = payload.get("paging", {})
    # Never return or follow next URLs, which can contain access tokens.
    return {
        "items": items,
        "cursor": paging.get("cursors", {}).get("after") if paging.get("next") else None,
        "sample": account.provider == "instagram_mock",
    }


def safe_remote_url(value, hosts):
    from urllib.parse import urlsplit

    p = urlsplit(str(value))
    host = p.hostname or ""
    return (
        str(value)[:2048]
        if p.scheme == "https" and not p.username and any(host == h or host.endswith("." + h) for h in hosts)
        else ""
    )


class LinkInput(StrictInput):
    media_ids: list[str] = Field(min_length=1, max_length=100)
    product_id: str | None = None


@router.put("/media/product")
def link_product(data: LinkInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace(db, user)
    if data.product_id:
        owned(db, Product, data.product_id, ws.id)
    rows = [owned(db, InstagramMedia, identity, ws.id) for identity in data.media_ids]
    for row in rows:
        row.product_id = data.product_id
    audit(db, user.id, "media.product_linked", data.product_id or "", count=len(rows))
    db.commit()
    return {"ok": True}


@router.get("/leads")
def leads(user: User = Depends(current_user), db: Session = Depends(get_db), offset: int = Query(0, ge=0)):
    return [
        serialize(row, LEAD_FIELDS)
        for row in db.scalars(
            select(Lead)
            .where(Lead.workspace_id == workspace(db, user).id)
            .order_by(Lead.last_interaction.desc())
            .offset(offset)
            .limit(100)
        )
    ]


class LeadInput(StrictInput):
    tags: list[str] = Field(default_factory=list, max_length=30)
    note: str = Field(default="", max_length=500)


@router.patch("/leads/{identity}")
def edit_lead(
    identity: str, data: LeadInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = owned(db, Lead, identity, workspace(db, user).id)
    if any(not t.strip() or len(t) > 60 for t in data.tags):
        raise HTTPException(422, "invalid_tags")
    row.tags = list(dict.fromkeys(data.tags))
    if data.note:
        row.notes = (row.notes + [{"text": data.note, "at": now_utc().isoformat()}])[-100:]
    db.commit()
    return serialize(row, LEAD_FIELDS)


@router.get("/executions/{identity}")
def execution_detail(identity: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = owned(db, Execution, identity, workspace(db, user).id)
    result = serialize(
        row,
        "id automation_id product_id media_id trigger event_id dry_run status detail context started_at completed_at created_at",
    )
    result.update(
        automation_name=db.get(Automation, row.automation_id).name,
        product_name=db.get(Product, row.product_id).name if row.product_id else None,
        media_caption=db.get(InstagramMedia, row.media_id).caption if row.media_id else None,
    )
    result["actions"] = [
        serialize(a, "id position kind status attempts result started_at completed_at")
        for a in db.scalars(
            select(ActionExecution)
            .where(ActionExecution.execution_id == row.id)
            .order_by(ActionExecution.position)
        )
    ]
    return result


@router.get("/commerce/metrics")
def metrics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace(db, user)
    statuses = db.execute(
        select(Execution.status, func.count())
        .where(Execution.workspace_id == ws.id, Execution.dry_run.is_(False))
        .group_by(Execution.status)
    ).all()
    counts = {
        "products": db.scalar(select(func.count()).select_from(Product).where(Product.workspace_id == ws.id)),
        "leads": db.scalar(select(func.count()).select_from(Lead).where(Lead.workspace_id == ws.id)),
    }
    return {"counts": counts, "executions": dict(statuses)}
