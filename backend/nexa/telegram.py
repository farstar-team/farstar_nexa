import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nexa.integration_config import integration_settings
from nexa.models import Account, Automation, Execution, TelegramLink, User
from nexa.security import audit, consume_token, workspace

TEXT = {
    "unlinked": "برای اتصال حساب، از بخش تلگرام در پنل نکسا پیوند اتصال بسازید.",
    "linked": "حساب تلگرام شما با موفقیت به نکسا متصل شد.",
    "invalid": "پیوند اتصال نامعتبر یا منقضی است. از پنل پیوند تازه‌ای بسازید.",
    "home": "به فاراستار نکسا خوش آمدید. یکی از گزینه‌ها را انتخاب کنید.",
    "empty": "هنوز موردی ثبت نشده است.",
    "accounts": "📱 حساب‌های متصل",
    "automations": "⚡ اتوماسیون‌ها",
    "stats": "📊 آمار",
    "panel": "🌐 ورود به پنل",
    "enable": "✅ فعال کردن",
    "disable": "⛔ غیرفعال کردن",
    "confirm": "تغییر وضعیت این اتوماسیون را تأیید می‌کنید؟",
    "yes": "تأیید",
    "back": "بازگشت",
    "updated": "وضعیت اتوماسیون به‌روز شد.",
    "channel_required": "برای استفاده از ربات ابتدا عضو کانال رسمی شوید.",
    "channel_check": "عضویت در کانال بررسی شد.",
}


def bot_call(method: str, payload: dict) -> dict:
    token = integration_settings().telegram_bot_token
    if not token:
        raise RuntimeError("telegram_not_configured")
    try:
        result = httpx.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=15)
        data = result.json()
        if not result.is_success or not data.get("ok"):
            raise RuntimeError("telegram_api_error")
        return data["result"]
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("telegram_api_unavailable") from None


def menu():
    return [[{"text": TEXT[key], "callback_data": key}] for key in ("accounts", "automations", "stats")] + [
        [{"text": "🚀 مینی‌اپ نکسا", "web_app": {"url": integration_settings().base_url + "/telegram-mini-app"}}],
        [{"text": TEXT["panel"], "url": integration_settings().base_url}],
    ]


def channel_is_member(telegram_id: str) -> bool:
    username = integration_settings().telegram_channel_username.strip()
    if not username:
        return True
    chat_id = username if username.startswith("@") or username.startswith("-") else "@" + username
    try:
        member = bot_call("getChatMember", {"chat_id": chat_id, "user_id": telegram_id})
    except RuntimeError:
        return False
    return member.get("status") in {"creator", "administrator", "member"} or (
        member.get("status") == "restricted" and member.get("is_member") is True
    )


def channel_keyboard():
    username = integration_settings().telegram_channel_username.strip().lstrip("@")
    return [
        [{"text": "عضویت در کانال", "url": "https://t.me/" + username}],
        [{"text": "بررسی عضویت", "callback_data": "channel:check"}],
    ]


def configure_webhook():
    import re

    config = integration_settings()
    if not config.base_url.startswith("https://") or not re.fullmatch(
        r"[A-Za-z0-9_-]{32,256}", config.telegram_webhook_secret
    ):
        raise ValueError("https_and_secret_required")
    bot = bot_call("getMe", {})
    if bot["username"].lower() != config.telegram_bot_username.lower():
        raise ValueError("bot_username_mismatch")
    bot_call(
        "setWebhook",
        {
            "url": config.public_urls["telegram_webhook"],
            "secret_token": config.telegram_webhook_secret,
            "allowed_updates": ["message", "callback_query"],
        },
    )
    bot_call(
        "setChatMenuButton",
        {"menu_button": {"type": "web_app", "text": "Nexa Mini App", "web_app": {"url": config.base_url + "/telegram-mini-app"}}},
    )


def handle_update(db: Session, data: dict):
    callback = data.get("callback_query")
    message = callback.get("message", {}) if callback else data.get("message", {})
    sender = (callback or message).get("from", {})
    chat = message.get("chat", {})
    if chat.get("type") != "private" or sender.get("is_bot"):
        return
    telegram_id = str(sender.get("id", ""))
    if str(chat.get("id", "")) != telegram_id:
        return
    text = message.get("text", "")
    reply = TEXT["home"]
    keyboard = menu()
    if text.startswith("/start ") and not callback:
        try:
            row = consume_token(db, text.split(" ", 1)[1], "telegram")
            user = db.get(User, row.user_id)
            if not user.active or db.scalar(
                select(TelegramLink).where(
                    (TelegramLink.user_id == user.id) | (TelegramLink.telegram_id == telegram_id)
                )
            ):
                raise ValueError("already_linked")
            db.add(TelegramLink(user_id=user.id, telegram_id=telegram_id))
            audit(db, user.id, "telegram.link")
            db.commit()
            reply = TEXT["linked"]
        except ValueError:
            db.rollback()
            reply = TEXT["invalid"]
    link = db.scalar(select(TelegramLink).where(TelegramLink.telegram_id == telegram_id))
    user = db.get(User, link.user_id) if link else None
    if not user or not user.active:
        reply, keyboard = TEXT["unlinked"], []
    elif integration_settings().telegram_channel_username and not channel_is_member(telegram_id):
        reply, keyboard = TEXT["channel_required"], channel_keyboard()
        if callback:
            bot_call("answerCallbackQuery", {"callback_query_id": callback["id"]})
    elif callback:
        ws = workspace(db, user)
        action = callback.get("data", "")
        if action == "channel:check":
            reply = TEXT["channel_check"] if channel_is_member(telegram_id) else TEXT["channel_required"]
            keyboard = menu() if channel_is_member(telegram_id) else channel_keyboard()
        if action == "accounts":
            reply = (
                "\n".join(
                    db.scalars(
                        select(Account.name).where(Account.workspace_id == ws.id, Account.active.is_(True))
                    )
                )
                or TEXT["empty"]
            )
        elif action == "automations":
            rules = list(db.scalars(select(Automation).where(Automation.workspace_id == ws.id).limit(30)))
            reply = TEXT["automations"] if rules else TEXT["empty"]
            keyboard = [[{"text": rule.name, "callback_data": "rule:" + rule.id}] for rule in rules]
        elif action == "stats":
            count = db.scalar(
                select(func.count()).select_from(Execution).where(Execution.workspace_id == ws.id)
            )
            reply = f"{TEXT['stats']}: {count}"
        elif action.startswith(("rule:", "toggle:", "confirm:")):
            parts = action.split(":")
            rule = db.scalar(
                select(Automation).where(Automation.id == parts[1], Automation.workspace_id == ws.id)
            )
            if rule:
                if parts[0] == "rule":
                    reply = rule.name
                    keyboard = [
                        [
                            {
                                "text": TEXT["disable" if rule.enabled else "enable"],
                                "callback_data": f"toggle:{rule.id}:{int(not rule.enabled)}",
                            }
                        ]
                    ]
                elif parts[0] == "toggle" and len(parts) == 3:
                    reply = TEXT["confirm"]
                    keyboard = [[{"text": TEXT["yes"], "callback_data": f"confirm:{rule.id}:{parts[2]}"}]]
                elif len(parts) == 3 and parts[2] in {"0", "1"}:
                    rule.enabled = parts[2] == "1"
                    rule.status = "ACTIVE" if rule.enabled else "PAUSED"
                    audit(db, user.id, "automation.toggle.telegram", rule.id, enabled=rule.enabled)
                    db.commit()
                    reply = TEXT["updated"]
        bot_call("answerCallbackQuery", {"callback_query_id": callback["id"]})
    bot_call(
        "sendMessage", {"chat_id": chat["id"], "text": reply, "reply_markup": {"inline_keyboard": keyboard}}
    )
