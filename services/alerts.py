"""Delivery of ops errors and user complaints to a SEPARATE Telegram bot, so
they never appear in the main user-facing bot. Configured via ALERTS_BOT_TOKEN
and ALERTS_CHAT_ID (falls back to the first admin id)."""
from __future__ import annotations

import logging
import time

import aiohttp

from config import settings

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org"
# Per-key cooldown so a looping error can't flood the alerts chat.
_last_sent: dict[str, float] = {}


async def send_alert(text: str, *, throttle_key: str | None = None, cooldown: float = 300.0) -> bool:
    """Send a message to the alerts bot. Returns True on success.

    When throttle_key is given, repeat alerts with the same key are suppressed
    for `cooldown` seconds (default 5 min) to avoid flooding."""
    token = settings.ALERTS_BOT_TOKEN.strip()
    chat_id = settings.alerts_chat_id
    if not token or not chat_id:
        return False

    if throttle_key is not None:
        now = time.monotonic()
        last = _last_sent.get(throttle_key)
        if last is not None and now - last < cooldown:
            return False
        _last_sent[throttle_key] = now

    url = f"{_API}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        status = await _post(url, payload)
    except Exception:
        logger.exception("Failed to send alert")
        return False
    if status != 200:
        logger.warning("Alert send failed: HTTP %s", status)
        return False
    return True


async def _post(url: str, payload: dict) -> int:
    """POST to the Telegram API and return the HTTP status. Split out so tests
    can stub the network."""
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            return resp.status
