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
BOT_URL = f"https://t.me/{BOT_USERNAME}"
# Письма с Gmail нередко уходят в «Спам» — об этом говорим и на сайте.
KEEP_OUT_OF_SPAM = "Чтобы наши письма не попадали в «Спам», добавьте этот адрес в контакты."

_BUTTON = (
    "text-decoration:none;padding:11px 18px;border-radius:6px;display:inline-block;"
    "margin:0 8px 8px 0"
)


def _site() -> str:
    return (settings.WEB_BASE_URL or "").strip().rstrip("/") or "https://unlockproject.site"


def _login_block(site: str, email: str, password: str) -> tuple[str, str]:
    """Вход в кабинет для аккаунта, который создала эта оплата: текст и HTML."""
    text = (
        "Мы создали вам личный кабинет:\n"
        f"  адрес: {site}/cabinet\n"
        f"  логин: {email}\n"
        f"  временный пароль: {password}\n"
        "Сменить пароль можно в кабинете.\n\n"
    )
    body = (
        '<div style="background:#f4f4f2;border-radius:8px;padding:14px 16px;margin:20px 0">'
        '<p style="margin:0 0 6px;font-weight:600">Мы создали вам личный кабинет</p>'
        f'<p style="margin:0">Адрес: <a href="{html.escape(site)}/cabinet">{html.escape(site)}/cabinet</a><br>'
        f"Логин: <b>{html.escape(email)}</b><br>"
        f'Временный пароль: <code style="font-size:16px">{html.escape(password)}</code></p>'
        '<p style="margin:6px 0 0;color:#555;font-size:14px">Сменить пароль можно в кабинете.</p>'
        "</div>"
    )
    return text, body


def build_letter(
    sub_url: str,
    plan_title: str,
    expires_at: datetime | None,
    *,
    login_email: str | None = None,
    temporary_password: str | None = None,
) -> tuple[str, str, str]:
    """Subject, plain text and HTML of the letter.

    login_email и temporary_password — только когда аккаунт создала эта оплата:
    тогда в письме и данные для входа в кабинет.
    """

    site = _site()
    connect = f"{site}/connect#sub={urllib.parse.quote(sub_url, safe='')}"
    until = expires_at.astimezone(_MSK).strftime("%d.%m.%Y") if expires_at else None
    active = f"Подписка «{plan_title}» активна до {until}." if until else f"Подписка «{plan_title}» активна."
    login_text = login_html = ""
    if login_email and temporary_password:
        login_text, login_html = _login_block(site, login_email, temporary_password)

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
        f"{login_text}"
        f"Личный кабинет: {site}/cabinet\n"
        f"Telegram-бот: {BOT_URL} — чтобы подписка была видна и в боте, отправьте ему /link "
        "и эту ссылку.\n\n"
        "Сохраните это письмо: по ссылке доступ восстанавливается даже без Telegram.\n"
        f"{KEEP_OUT_OF_SPAM}\n\n"
        f"Поддержка: {SUPPORT_URL} или просто ответьте на это письмо."
    )

    safe_url = html.escape(sub_url)
    safe_connect = html.escape(connect, quote=True)
    body = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1a1a1a;max-width:560px">'
        '<p style="font-size:18px;font-weight:600;margin:0 0 12px">Спасибо за оплату!</p>'
        f"<p>{html.escape(active)}</p>"
        '<p style="margin:20px 0 12px">'
        f'<a href="{safe_connect}" style="background:#2481cc;color:#fff;{_BUTTON}">Подключить VPN</a>'
        f'<a href="{BOT_URL}" style="background:#fff;color:#2481cc;border:1px solid #2481cc;{_BUTTON}">'
        "Открыть Telegram-бота</a></p>"
        "<p>Ваша ссылка-подписка:<br>"
        f'<code style="word-break:break-all">{safe_url}</code></p>'
        "<p>Её можно добавить в приложение Happ вручную: «+» → «Вставить из буфера».</p>"
        f"{login_html}"
        f'<p>Личный кабинет: <a href="{html.escape(site)}/cabinet">{html.escape(site)}/cabinet</a><br>'
        f'Telegram-бот: <a href="{BOT_URL}">@{BOT_USERNAME}</a> — чтобы подписка была видна и в боте, '
        "отправьте ему <b>/link</b> и эту ссылку.</p>"
        '<p style="color:#555;font-size:14px">Сохраните это письмо: по ссылке доступ '
        "восстанавливается даже без Telegram.<br>"
        f"{html.escape(KEEP_OUT_OF_SPAM)}<br>"
        f'Поддержка: <a href="{SUPPORT_URL}">@unlock_support_bot</a> или ответьте на это письмо.</p>'
        "</div>"
    )
    return subject, text, body


def build_reset_letter(reset_url: str) -> tuple[str, str, str]:
    """Письмо «Забыли пароль?»: subject, текст, HTML."""
    subject = "UnLock VPN: восстановление пароля"
    text = (
        "Вы запросили новый пароль для личного кабинета UnLock VPN.\n\n"
        f"Задать новый пароль: {reset_url}\n\n"
        "Ссылка действует 1 час и срабатывает один раз.\n"
        "Если вы ничего не запрашивали — просто удалите это письмо, пароль останется прежним.\n\n"
        f"Поддержка: {SUPPORT_URL}"
    )
    body = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1a1a1a;max-width:560px">'
        '<p style="font-size:18px;font-weight:600;margin:0 0 12px">Восстановление пароля</p>'
        "<p>Вы запросили новый пароль для личного кабинета UnLock VPN.</p>"
        '<p style="margin:20px 0">'
        f'<a href="{html.escape(reset_url, quote=True)}" style="background:#2481cc;color:#fff;{_BUTTON}">'
        "Задать новый пароль</a></p>"
        '<p style="color:#555;font-size:14px">Ссылка действует 1 час и срабатывает один раз.<br>'
        "Если вы ничего не запрашивали — просто удалите это письмо, пароль останется прежним.<br>"
        f'Поддержка: <a href="{SUPPORT_URL}">@unlock_support_bot</a></p>'
        "</div>"
    )
    return subject, text, body


def reset_url(token: str) -> str:
    # Токен во фрагменте: он не уходит на сервер и не попадает в журналы.
    return f"{_site()}/cabinet/reset#t={urllib.parse.quote(token, safe='')}"


async def send_reset_letter(email: str, token: str) -> bool:
    """Best effort, как и письмо с подпиской."""
    if not email or not token or not mailer.is_configured():
        return False
    subject, text, body = build_reset_letter(reset_url(token))
    try:
        return await mailer.send_email(email, subject, text, html=body)
    except Exception:  # noqa: BLE001
        logger.exception("Password reset letter failed")
        return False


async def send_subscription_letter(
    email: str,
    sub_url: str,
    plan_title: str,
    expires_at: datetime | None,
    *,
    login_email: str | None = None,
    temporary_password: str | None = None,
) -> bool:
    """Best effort: a failed letter is logged, never raised into the payment flow."""

    if not email or not sub_url or not mailer.is_configured():
        return False
    subject, text, body = build_letter(
        sub_url, plan_title, expires_at, login_email=login_email, temporary_password=temporary_password
    )
    try:
        return await mailer.send_email(email, subject, text, html=body)
    except Exception:  # noqa: BLE001 - delivery must not undo a completed payment
        logger.exception("Subscription letter to a web buyer failed")
        return False
