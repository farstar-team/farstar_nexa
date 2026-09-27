from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexa.db import get_db
from nexa.models import Product, User, WorkspaceMember
from nexa.models import Session as LoginSession
from nexa.security import audit, current_user, hasher, validate_password, workspace_owner

router = APIRouter(prefix="/api/team", tags=["team"])


class MemberInput(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,64}$")
    email: EmailStr
    password: str = Field(max_length=256)
    product_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        return validate_password(value)


class MemberUpdate(BaseModel):
    active: bool | None = None
    password: str | None = Field(default=None, max_length=256)
    product_ids: list[str] | None = Field(default=None, max_length=100)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        return validate_password(value) if value else value


def _products(db: Session, workspace_id: str, product_ids: list[str]):
    product_ids = list(dict.fromkeys(product_ids))
    rows = list(db.scalars(select(Product).where(Product.workspace_id == workspace_id, Product.id.in_(product_ids)))) if product_ids else []
    if len(rows) != len(product_ids):
        raise HTTPException(400, "invalid_product_assignment")
    return rows


def _item(db: Session, row: WorkspaceMember):
    user = db.get(User, row.user_id)
    products = list(db.scalars(select(Product).where(Product.id.in_(row.product_ids or [])))) if row.product_ids else []
    return {
        "id": row.user_id,
        "username": user.username,
        "email": user.email,
        "role": row.role,
        "active": row.active and user.active,
        "product_ids": row.product_ids or [],
        "products": [{"id": p.id, "name": p.name} for p in products],
        "created_at": row.created_at.isoformat() + "Z",
    }


@router.get("")
def members(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace_owner(db, user)
    return [_item(db, row) for row in db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id).order_by(WorkspaceMember.created_at.desc()))]


@router.post("", status_code=201)
def create_member(data: MemberInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace_owner(db, user)
    _products(db, ws.id, data.product_ids)
    row = User(
        username=data.username.lower(),
        email=str(data.email).lower(),
        password_hash=hasher.hash(data.password),
        role="USER",
    )
    db.add(row)
    try:
        db.flush()
        member = WorkspaceMember(workspace_id=ws.id, user_id=row.id, product_ids=list(dict.fromkeys(data.product_ids)))
        db.add(member)
        audit(db, user.id, "team.member_created", row.id, product_count=len(data.product_ids))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "account_exists") from None
    return _item(db, member)


@router.patch("/{identity}")
def update_member(identity: str, data: MemberUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws = workspace_owner(db, user)
    member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == identity, WorkspaceMember.workspace_id == ws.id))
    target = db.get(User, identity)
    if not member or not target:
        raise HTTPException(404, "not_found")
    if data.product_ids is not None:
        _products(db, ws.id, data.product_ids)
        member.product_ids = list(dict.fromkeys(data.product_ids))
    if data.active is not None:
        member.active = data.active
        target.active = data.active
    if data.password:
        target.password_hash = hasher.hash(data.password)
    if data.active is False or data.password:
        db.execute(delete(LoginSession).where(LoginSession.user_id == target.id))
    audit(db, user.id, "team.member_updated", target.id, active=data.active, password_changed=bool(data.password))
    db.commit()
    return _item(db, member)
