"""Outgoing email over plain SMTP (stdlib) — currently used for чеки.

Provider-agnostic: point SMTP_* at Gmail (app password), Resend's SMTP
endpoint, or any other relay. Port 465 speaks implicit TLS, any other port
goes through STARTTLS. Best-effort by design: a failed send is logged and
returns False, it must never break payment delivery.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from config import settings

logger = logging.getLogger(__name__)

_SEND_TIMEOUT_SECONDS = 20


def is_configured() -> bool:
    return bool(settings.SMTP_HOST.strip() and settings.SMTP_FROM.strip())


def _send_sync(message: EmailMessage) -> None:
    host = settings.SMTP_HOST.strip()
    port = int(settings.SMTP_PORT)
    context = ssl.create_default_context()
    if port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=_SEND_TIMEOUT_SECONDS, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=_SEND_TIMEOUT_SECONDS)
    with client:
        if port != 465:
            client.starttls(context=context)
        if settings.SMTP_USER.strip():
            client.login(settings.SMTP_USER.strip(), settings.smtp_password)
        client.send_message(message)


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send one email; returns True on success, False (logged) on any failure."""
    if not is_configured() or not to.strip():
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM.strip()
    message["To"] = to.strip()
    message["Subject"] = subject
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")

    try:
        await asyncio.to_thread(_send_sync, message)
        return True
    except Exception:  # noqa: BLE001 - email is best-effort, never propagate
        logger.exception("Failed to send email to %s (subject=%r)", to, subject)
        return False
