"""Static banner images shown as photo headers on key bot screens.

Each asset is uploaded to Telegram once per process; the returned file_id is
cached and reused so the file isn't re-read/re-uploaded on every send. If an
asset is missing or Telegram rejects the photo, we fall back to a plain text
message — a missing banner must never break a flow (e.g. the expiry notifier).
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

WELCOME_BANNER = "assets/banner_welcome.jpg"  # приветственный/стартовый экран
CABINET_BANNER = "assets/banner_cabinet.jpg"  # личный кабинет
EXPIRED_BANNER = "assets/banner_expired.jpg"  # подписка закончилась

# banner path -> Telegram file_id (populated on first successful upload)
_file_ids: dict[str, str] = {}


def pick_start_banner(is_new_user: bool) -> str:
    """A first-ever /start greets with the welcome/sell screen; every later
    /start opens the personal cabinet. (Keyed off first-touch rather than
    subscription state, since new users get an auto-trial on their first /start.)"""
    return WELCOME_BANNER if is_new_user else CABINET_BANNER


async def send_banner(
    bot: Bot,
    chat_id: int,
    banner_path: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    photo = _file_ids.get(banner_path) or FSInputFile(banner_path)
    try:
        sent = await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup)
    except Exception:  # noqa: BLE001 - never let a missing/broken banner break the flow
        logger.warning("Banner %s unavailable; falling back to text", banner_path, exc_info=True)
        await bot.send_message(chat_id, caption, reply_markup=reply_markup)
        return
    if banner_path not in _file_ids and sent.photo:
        _file_ids[banner_path] = sent.photo[-1].file_id
