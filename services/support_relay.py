"""Two-bot support relay (runs as its own process: systemd `unlock-support`).

Flow:
  user → writes to the SUPPORT bot (@SUPPORT_BOT_USERNAME)
       → ticket is copied to every staff chat in the REPORTS bot
         (the owner's ALERTS_CHAT_ID first, then SUPPORT_AGENT_IDS)
  staff → REPLIES to their copy of the ticket in the REPORTS bot
       → the reply is delivered back to the user via the SUPPORT bot,
         and every other staff chat is told who answered and what

Both bots are polled here. The main VPN bot only *sends* to the reports bot
(HTTP), so there is no getUpdates conflict on the reports token.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import uuid

import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("support_relay")

# One key per copy of a ticket: (staff chat, message there) -> user + ticket.
# Message ids are per chat, so the chat is part of the key.
_TICKET_KEY = "support:ticket:{chat}:{mid}"
# Before 19.09.2026 there was one staff chat and the key had no chat in it.
_LEGACY_TICKET_KEY = "support:ticket:{mid}"
# Every copy of one ticket, so a reply in one chat can be announced in the rest.
_COPIES_KEY = "support:copies:{ticket}"
_TICKET_TTL = 60 * 60 * 24 * 30  # 30 days


def support_chats(admin_chat: str, agent_ids: list[int]) -> list[int]:
    """Staff chats that receive tickets: the owner's first, no repeats."""
    chats = [int(admin_chat)] if str(admin_chat).strip() else []
    return list(dict.fromkeys([*chats, *agent_ids]))


def _record(user_id: int, ticket_id: str) -> str:
    return json.dumps({"user": user_id, "ticket": ticket_id})


class TicketBook:
    """Which client a ticket copy belongs to, and where its other copies are."""

    def __init__(self, redis) -> None:
        self.redis = redis

    async def remember(self, ticket_id: str, user_id: int, copies: list[tuple[int, int]]) -> None:
        for chat, mid in copies:
            await self.redis.set(_TICKET_KEY.format(chat=chat, mid=mid), _record(user_id, ticket_id), ex=_TICKET_TTL)
        await self.redis.set(_COPIES_KEY.format(ticket=ticket_id), json.dumps(copies), ex=_TICKET_TTL)

    async def lookup(self, chat_id: int, mid: int, *, legacy: bool = False) -> tuple[int, str | None] | None:
        raw = await self.redis.get(_TICKET_KEY.format(chat=chat_id, mid=mid))
        if raw:
            data = json.loads(raw)
            return int(data["user"]), data.get("ticket")
        if legacy:
            raw = await self.redis.get(_LEGACY_TICKET_KEY.format(mid=mid))
            if raw:
                return int(raw), None
        return None

    async def copies(self, ticket_id: str) -> list[tuple[int, int]]:
        raw = await self.redis.get(_COPIES_KEY.format(ticket=ticket_id))
        return [(int(chat), int(mid)) for chat, mid in json.loads(raw)] if raw else []


def _ticket_text(message: Message) -> str:
    user = message.from_user
    uname = f"@{user.username}" if user.username else "—"
    return (
        "🆘 <b>Обращение в поддержку</b>\n"
        f"От: {html.escape(user.full_name or '—')} ({uname})\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"{html.escape(message.text or '')}\n\n"
        "<i>↩️ Ответьте на это сообщение, чтобы ответить пользователю.</i>"
    )


async def forward_ticket(message: Message, *, reports_bot, book: TicketBook, chats: list[int]) -> None:
    """Copy a client's message to every staff chat and remember the copies."""
    user = message.from_user
    if user is None:
        return
    text = _ticket_text(message)
    ticket_id = uuid.uuid4().hex[:12]
    copies: list[tuple[int, int]] = []
    for chat in chats:
        try:
            sent = await reports_bot.send_message(chat, text)
        except Exception:
            # Usually a colleague who never pressed Start in the reports bot —
            # the others must still get the ticket.
            logger.exception("Ticket copy to chat %s failed", chat)
            continue
        copies.append((chat, sent.message_id))
    await book.remember(ticket_id, user.id, copies)
    if copies:
        await message.answer("✅ Сообщение отправлено в поддержку. Ответ придёт сюда же.")
    else:
        await message.answer("⚠️ Не удалось передать сообщение. Попробуйте ещё раз через минуту.")


def _author(message: Message) -> str:
    user = message.from_user
    if user is not None and user.username:
        return f"@{user.username}"
    return html.escape((user.full_name if user else "") or "сотрудник")


async def relay_reply(
    message: Message, *, support_bot, reports_bot, book: TicketBook, chats: list[int]
) -> None:
    """Deliver a staff reply to the client and tell the other staff chats."""
    chat_id = message.chat.id
    if chat_id not in chats:
        return
    found = await book.lookup(chat_id, message.reply_to_message.message_id, legacy=chat_id == chats[0])
    if found is None:
        return  # reply to a non-ticket alert (or expired ticket) — ignore
    user_id, ticket_id = found
    text = message.text or message.caption or ""
    try:
        await support_bot.send_message(user_id, f"💬 <b>Ответ поддержки:</b>\n{html.escape(text)}")
    except Exception:
        logger.exception("Failed to deliver support reply to user_id=%s", user_id)
        await message.reply("❌ Не удалось доставить (пользователь остановил бота?).")
        return
    await message.reply("✅ Доставлено пользователю.")
    if not ticket_id:
        return
    note = f"↩️ Ответил(а) {_author(message)}:\n{html.escape(text)}"
    for other_chat, other_mid in await book.copies(ticket_id):
        if other_chat == chat_id:
            continue
        try:
            await reports_bot.send_message(other_chat, note, reply_to_message_id=other_mid)
        except Exception:
            logger.exception("Could not tell chat %s about the reply", other_chat)


async def main() -> None:
    if not settings.SUPPORT_BOT_TOKEN or not settings.ALERTS_BOT_TOKEN:
        raise SystemExit("SUPPORT_BOT_TOKEN and ALERTS_BOT_TOKEN are required")
    chats = support_chats(settings.alerts_chat_id, settings.support_agent_ids)
    if not chats:
        raise SystemExit("ALERTS_CHAT_ID or ADMIN_IDS is required")

    props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    support_bot = Bot(token=settings.SUPPORT_BOT_TOKEN, default=props)
    reports_bot = Bot(token=settings.ALERTS_BOT_TOKEN, default=props)
    redis = aioredis.from_url(settings.REDIS_URL)
    book = TicketBook(redis)

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
        await forward_ticket(message, reports_bot=reports_bot, book=book, chats=chats)

    @reports_dp.message(CommandStart())
    async def on_staff_start(message: Message) -> None:
        if message.chat.id not in chats:
            return
        await message.answer(
            "✅ Сюда будут приходить обращения в поддержку и технические уведомления.\n\n"
            "Чтобы ответить клиенту, ответьте (reply) на сообщение с обращением."
        )

    @reports_dp.message(F.reply_to_message)
    async def on_admin_reply(message: Message) -> None:
        await relay_reply(message, support_bot=support_bot, reports_bot=reports_bot, book=book, chats=chats)

    logger.info("Support relay started — staff chats: %s", ", ".join(map(str, chats)))
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
