"""Tribute card-payment integration helpers.

Tribute posts webhooks (new_subscription / new_digital_product) signed with an
HMAC-SHA256 `trbt-signature` header over the raw body. We verify the signature,
map the Tribute product/subscription id to one of our plans, and DM the buyer
their subscription link via the main bot. Amounts arrive in minor units.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging

import aiohttp

from config import settings

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"


def verify_signature(raw_body: bytes, signature: str) -> bool:
    """True if `signature` is a valid HMAC-SHA256 of the raw body using the key."""
    key = settings.TRIBUTE_API_KEY.strip()
    if not key:
        return False
    expected = hmac.new(key.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())


def plan_for(tribute_id: object) -> str | None:
    """Map a Tribute product/subscription id to our plan code (with fallback)."""
    if tribute_id is not None:
        mapped = settings.tribute_plan_map_dict.get(str(tribute_id))
        if mapped:
            return mapped
    return settings.TRIBUTE_DEFAULT_PLAN.strip() or None


async def deliver_subscription(telegram_id: int, sub_url: str) -> bool:
    """DM the buyer their subscription link via the main bot (HTTP sendMessage).

    Sends the link plus a button to the site's /connect page with one-tap app
    import and setup instructions — no QR image is pushed."""
    from services.subscription import connect_page_url

    token = settings.bot_token
    if not token or not sub_url:
        return False
    text = (
        "✅ <b>Оплата получена — подписка активна!</b>\n\n"
        "🔗 Ваша ссылка-подписка:\n"
        f"<code>{html.escape(sub_url)}</code>\n\n"
        "Нажмите «Подключить VPN» — откроется страница с приложениями и пошаговой инструкцией."
    )
    payload: dict[str, object] = {
        "chat_id": telegram_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    connect_url = connect_page_url(sub_url)
    if connect_url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🔗 Подключить VPN", "url": connect_url}]]
        }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_TELEGRAM_API}/bot{token}/sendMessage",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return resp.status == 200
    except Exception:
        logger.exception("Failed to deliver Tribute subscription to %s", telegram_id)
        return False
