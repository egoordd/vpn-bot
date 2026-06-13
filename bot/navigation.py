"""Screen navigation helper.

`show_screen` renders a text screen on the message a callback is attached to.
If that message carries a photo (banner, QR code, WireGuard config), the photo
message is deleted and a fresh text message is sent — otherwise editing only the
caption would leave the image stuck on screen. Plain text messages are edited
in place so navigation stays in one bubble.
"""

from __future__ import annotations

import logging

from aiogram.types import CallbackQuery, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def show_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    message = callback.message
    if message is None:
        return

    if getattr(message, "photo", None):
        try:
            await message.delete()
        except Exception:
            logger.debug("Could not delete photo message during navigation", exc_info=True)
        await message.answer(text, reply_markup=reply_markup)
        return

    await message.edit_text(text, reply_markup=reply_markup)
