"""Optional SMTP delivery for password and product notifications.

SMTP credentials are loaded through integration_settings(), which decrypts
values stored in SystemSetting. This module deliberately never logs message
content or credentials.
"""

import smtplib
import ssl
from email.message import EmailMessage

from nexa.integration_config import integration_settings


def configured() -> bool:
    config = integration_settings()
    return bool(config.smtp_host and config.smtp_from)


def send_email(to: str, subject: str, body: str) -> None:
    config = integration_settings()
    if not config.smtp_host or not config.smtp_from:
        raise RuntimeError("email_not_configured")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = config.smtp_from, to, subject
    message.set_content(body)
    security = config.smtp_security.lower().strip()
    context = ssl.create_default_context()
    port = int(config.smtp_port)
    if security == "ssl":
        with smtplib.SMTP_SSL(config.smtp_host, port, context=context, timeout=15) as client:
            if config.smtp_username:
                client.login(config.smtp_username, config.smtp_password)
            client.send_message(message)
        return
    with smtplib.SMTP(config.smtp_host, port, timeout=15) as client:
        if security == "starttls":
            client.starttls(context=context)
        if config.smtp_username:
            client.login(config.smtp_username, config.smtp_password)
        client.send_message(message)
