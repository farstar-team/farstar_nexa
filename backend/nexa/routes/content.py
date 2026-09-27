from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from nexa.db import get_db
from nexa.models import SystemSetting, User

router = APIRouter(prefix="/api", tags=["content"])

CONTENT_DEFAULTS = {
    "landing.kicker": "فروش اجتماعی هوشمند",
    "landing.title": "پاسخ سریع‌تر، فروش منظم‌تر، تجربه‌ای حرفه‌ای برای مشتری",
    "landing.description": "Farstar Nexa پیام‌ها و کامنت‌های شبکه‌های اجتماعی را به فرایند فروش قابل مدیریت تبدیل می‌کند؛ از نمایش قیمت تا ثبت سرنخ و پیگیری.",
    "landing.cta": "شروع کار با Nexa",
    "landing.features_title": "همه چیز برای فروش اجتماعی در یکجا",
    "support.title": "پشتیبانی فاراستار Nexa",
    "support.subtitle": "از راه ارتباطی دلخواه با تیم پشتیبانی در تماس باشید.",
    "support.telegram": "",
    "support.instagram": "",
    "support.channel": "",
    "support.email": "",
    "support.hours": "شنبه تا چهارشنبه، ساعت ۹ تا ۱۸",
}


def values(db: Session):
    rows = db.scalars(select(SystemSetting).where(SystemSetting.key.in_(CONTENT_DEFAULTS)))
    stored = {row.key: row.value for row in rows}
    return {key: stored.get(key, default) for key, default in CONTENT_DEFAULTS.items()}


@router.get("/content")
def public_content(db: Session = Depends(get_db)):
    return values(db)


def admin_content(db: Session, user: User):
    # Kept as a helper for the admin router; access is enforced there.
    return values(db)
