"""Two-bot support relay (runs as its own process: systemd `unlock-support`).

Flow:
  user → writes to the SUPPORT bot (@SUPPORT_BOT_USERNAME)
       → ticket is forwarded to the REPORTS bot (admin chat)
  admin → REPLIES to the ticket message in the REPORTS bot
       → the reply is delivered back to the user via the SUPPORT bot

Both bots are polled here. The main VPN bot only *sends* to the reports bot
(HTTP), so there is no getUpdates conflict on the reports token.
"""
from __future__ import annotations

import asyncio
import html
import logging

import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("support_relay")

# Maps a reports-bot message_id -> support user id, so an admin reply routes back.
_TICKET_KEY = "support:ticket:{mid}"
_TICKET_TTL = 60 * 60 * 24 * 30  # 30 days


async def main() -> None:
    if not settings.SUPPORT_BOT_TOKEN or not settings.ALERTS_BOT_TOKEN:
        raise SystemExit("SUPPORT_BOT_TOKEN and ALERTS_BOT_TOKEN are required")
    admin_chat = settings.alerts_chat_id
    if not admin_chat:
        raise SystemExit("ALERTS_CHAT_ID or ADMIN_IDS is required")

    props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    support_bot = Bot(token=settings.SUPPORT_BOT_TOKEN, default=props)
    reports_bot = Bot(token=settings.ALERTS_BOT_TOKEN, default=props)
    redis = aioredis.from_url(settings.REDIS_URL)

    support_dp = Dispatcher()
    reports_dp = Dispatcher()

    @support_dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        await message.answer(
            "👋 Это поддержка <b>UnLock VPN</b>.\n\n"
            "Опишите проблему одним сообщением — мы ответим прямо здесь."
        )

    @support_dp.message(F.text)
    async def on_user_message(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        uname = f"@{user.username}" if user.username else "—"
        ticket = (
            "🆘 <b>Обращение в поддержку</b>\n"
            f"От: {html.escape(user.full_name or '—')} ({uname})\n"
            f"ID: <code>{user.id}</code>\n\n"
            f"{html.escape(message.text)}\n\n"
            "<i>↩️ Ответьте на это сообщение, чтобы ответить пользователю.</i>"
        )
        sent = await reports_bot.send_message(admin_chat, ticket)
        await redis.set(_TICKET_KEY.format(mid=sent.message_id), user.id, ex=_TICKET_TTL)
        await message.answer("✅ Сообщение отправлено в поддержку. Ответ придёт сюда же.")

    @reports_dp.message(F.reply_to_message)
    async def on_admin_reply(message: Message) -> None:
        if str(message.chat.id) != str(admin_chat):
            return
        raw = await redis.get(_TICKET_KEY.format(mid=message.reply_to_message.message_id))
        if not raw:
            return  # reply to a non-ticket alert (or expired ticket) — ignore
        user_id = int(raw)
        text = message.text or message.caption or ""
        try:
            await support_bot.send_message(user_id, f"💬 <b>Ответ поддержки:</b>\n{html.escape(text)}")
            await message.reply("✅ Доставлено пользователю.")
        except Exception:
            logger.exception("Failed to deliver support reply to user_id=%s", user_id)
            await message.reply("❌ Не удалось доставить (пользователь остановил бота?).")

    logger.info("Support relay started — polling support + reports bots")
    try:
        await asyncio.gather(
            support_dp.start_polling(support_bot, handle_signals=False),
            reports_dp.start_polling(reports_bot, handle_signals=False),
        )
    finally:
        await support_bot.session.close()
        await reports_bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
