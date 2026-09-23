from sqlalchemy import select

from nexa.config import Settings, settings
from nexa.db import SessionLocal
from nexa.models import SystemSetting
from nexa.security import decrypt

FIELDS = {
    "meta_app_id",
    "meta_app_secret",
    "meta_verify_token",
    "telegram_bot_token",
    "telegram_bot_username",
    "telegram_webhook_secret",
}


def integration_settings() -> Settings:
    with SessionLocal() as db:
        rows = db.scalars(select(SystemSetting).where(SystemSetting.key.in_(FIELDS)))
        values = {row.key: decrypt(row.value) for row in rows}
    return settings().model_copy(update=values)
