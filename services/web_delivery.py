"""The subscription link, by email, for buyers who have no Telegram chat.

A purchase on the website lands on an email-only account: there is no chat to
message, so the success page used to be the only place the link ever appeared.
On a phone the payment often finishes in the bank's app and comes back in a
different browser, where that page cannot tell which order it is for — the buyer
paid and saw nothing, then found "email already taken" when trying to register.
This letter makes delivery independent of the page.
"""

from __future__ import annotations

import html
import logging
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

from config import settings
from services import mailer

logger = logging.getLogger(__name__)

_MSK = ZoneInfo("Europe/Moscow")
SUPPORT_URL = "https://t.me/unlock_support_bot"
BOT_USERNAME = "unlkvpn_bot"


def _site() -> str:
    return (settings.WEB_BASE_URL or "").strip().rstrip("/") or "https://unlockproject.site"


def build_letter(sub_url: str, plan_title: str, expires_at: datetime | None) -> tuple[str, str, str]:
    """Subject, plain text and HTML of the letter."""

    site = _site()
    connect = f"{site}/connect#sub={urllib.parse.quote(sub_url, safe='')}"
    until = expires_at.astimezone(_MSK).strftime("%d.%m.%Y") if expires_at else None
    active = f"Подписка «{plan_title}» активна до {until}." if until else f"Подписка «{plan_title}» активна."

    subject = "UnLock VPN: ваша подписка"
    text = (
        "Спасибо за оплату!\n"
        f"{active}\n\n"
        "Ваша ссылка-подписка:\n"
        f"{sub_url}\n\n"
        "Как подключиться:\n"
        f"1. Откройте страницу подключения: {connect}\n"
        "   Там приложения для телефона и компьютера и пошаговая инструкция.\n"
        "2. Или добавьте ссылку в приложение Happ вручную: «+» → «Вставить из буфера».\n\n"
        f"Личный кабинет: {site}/cabinet — вкладка «По ссылке», вставьте ссылку выше.\n"
        f"Чтобы подписка была видна в Telegram-боте @{BOT_USERNAME}, отправьте боту /link "
        "и эту ссылку.\n\n"
        "Сохраните это письмо: по ссылке доступ восстанавливается даже без Telegram.\n\n"
        f"Поддержка: {SUPPORT_URL} или просто ответьте на это письмо."
    )

    safe_url = html.escape(sub_url)
    safe_connect = html.escape(connect, quote=True)
    body = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1a1a1a;max-width:560px">'
        '<p style="font-size:18px;font-weight:600;margin:0 0 12px">Спасибо за оплату!</p>'
        f"<p>{html.escape(active)}</p>"
        '<p style="margin:20px 0">'
        f'<a href="{safe_connect}" style="background:#2481cc;color:#fff;text-decoration:none;'
        'padding:11px 18px;border-radius:6px;display:inline-block">Подключить VPN</a></p>'
        "<p>Ваша ссылка-подписка:<br>"
        f'<code style="word-break:break-all">{safe_url}</code></p>'
        "<p>Её можно добавить в приложение Happ вручную: «+» → «Вставить из буфера».</p>"
        f'<p>Личный кабинет: <a href="{html.escape(site)}/cabinet">{html.escape(site)}/cabinet</a> '
        "— вкладка «По ссылке».<br>"
        f"Чтобы подписка была видна в Telegram-боте @{BOT_USERNAME}, отправьте боту "
        "<b>/link</b> и эту ссылку.</p>"
        '<p style="color:#555;font-size:14px">Сохраните это письмо: по ссылке доступ '
        "восстанавливается даже без Telegram.<br>"
        f'Поддержка: <a href="{SUPPORT_URL}">@unlock_support_bot</a> или ответьте на это письмо.</p>'
        "</div>"
    )
    return subject, text, body


async def send_subscription_letter(
    email: str, sub_url: str, plan_title: str, expires_at: datetime | None
) -> bool:
    """Best effort: a failed letter is logged, never raised into the payment flow."""

    if not email or not sub_url or not mailer.is_configured():
        return False
    subject, text, body = build_letter(sub_url, plan_title, expires_at)
    try:
        return await mailer.send_email(email, subject, text, html=body)
    except Exception:  # noqa: BLE001 - delivery must not undo a completed payment
        logger.exception("Subscription letter to a web buyer failed")
        return False
