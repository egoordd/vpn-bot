"""One-off broadcast to bot users, with a dry run by default.

The bot has no broadcast handler and does not need one: a mailing is a rare,
deliberate act, and putting it behind a command would make it one slip away.
This script keeps it outside the bot, shows exactly who would receive what, and
sends only when --send is passed.

    python3 scripts/broadcast.py                 # preview, active subscribers
    python3 scripts/broadcast.py --audience all  # preview, everyone with a chat
    python3 scripts/broadcast.py --audience all --send

Telegram silently drops a chat the user has blocked, so failures are counted and
listed rather than retried — a second attempt would fail the same way.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import Subscription, User


# Telegram tolerates ~30 messages/second; one every 1.5s stays far inside that
# and keeps a stalled send from cascading.
SEND_INTERVAL_SECONDS = 1.5

MESSAGE = (
    "<b>Внесённые изменения</b>\n\n"
    "• В боте появилась команда /link — привязывает подписку, купленную на сайте, "
    "к вашему аккаунту в Telegram.\n\n"
    "• На сайте появился вход по ссылке подписки — вкладка «По ссылке» на странице "
    "входа в личный кабинет.\n\n"
    "<b>Зачем это нужно</b>\n\n"
    "Сайт и бот раньше не знали друг о друге. Человек оплачивал на сайте, открывал "
    "бота и видел пустоту. Деньги никуда не пропадали, подписка просто лежала на "
    "второй учётной записи, но со стороны это выглядело как «оплатил и потерял». "
    "Теперь записи объединяются, и подписка видна в обоих местах.\n\n"
    "Вход по ссылке закрывает вторую половину той же проблемы. Если покупали без "
    "пароля, попасть в личный кабинет было нечем. Теперь вставляете ссылку подписки, "
    "задаёте пароль и заходите как обычно.\n\n"
    "Переподключать ничего не нужно, ссылка в приложении остаётся прежней.\n\n"
    "<b>Поддержка</b>\n"
    "@unlock_support_bot"
)

KEYBOARD = {
    "inline_keyboard": [
        # The callback the /link flow already answers, so the whole thing is one
        # tap from the broadcast itself.
        [{"text": "🔗 Привязать подписку", "callback_data": "link_subscription"}],
        [{"text": "🌐 Личный кабинет", "url": "https://unlockproject.site/cabinet"}],
        [{"text": "💬 Поддержка", "url": "https://t.me/unlock_support_bot"}],
    ]
}


async def load_recipients(
    session, audience: str, telegram_ids: list[int] | None = None
) -> list[User]:
    """Users with a real Telegram chat behind them.

    Website buyers carry a synthetic negative id and no chat, so a DM to them
    would fail; they are reachable by email instead.
    """

    query = select(User).where(User.telegram_id > 0)
    if telegram_ids:
        # Explicit recipients bypass the audience filter: a test send must reach
        # the named account even when it has no active subscription.
        query = query.where(User.telegram_id.in_(telegram_ids))
    elif audience == "active":
        now = datetime.now(timezone.utc)
        query = query.join(Subscription, Subscription.user_id == User.id).where(
            Subscription.expires_at > now
        )
    users = list((await session.execute(query)).scalars().unique())
    users.sort(key=lambda u: u.id)
    return users


async def send(api_base: str, chat_id: int) -> tuple[bool, str]:
    payload = {
        "chat_id": chat_id,
        "text": MESSAGE,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
        "reply_markup": KEYBOARD,
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{api_base}/sendMessage", json=payload) as response:
            body = await response.json(content_type=None)
    if body.get("ok"):
        return True, "доставлено"
    return False, str(body.get("description") or f"HTTP {response.status}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audience",
        choices=("active", "all"),
        default="active",
        help="active — только с действующей подпиской; all — все, кто заходил в бота",
    )
    parser.add_argument(
        "telegram_ids",
        nargs="*",
        type=int,
        help="кому отправить поимённо; без них берётся вся аудитория",
    )
    parser.add_argument("--send", action="store_true", help="отправить (иначе только показать)")
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_pool() as session:
            recipients = await load_recipients(
                session, args.audience, args.telegram_ids or None
            )
    finally:
        await engine.dispose()

    if not recipients:
        print("Некому отправлять.")
        return 1

    mode = "ОТПРАВКА" if args.send else "предпросмотр"
    print(f"Получателей: {len(recipients)}  |  аудитория: {args.audience}  |  режим: {mode}\n")

    if not args.send:
        print("--- текст сообщения ---")
        import re
        preview = re.sub(r'<a href="([^"]+)">(.*?)</a>', r"\2  →  \1", MESSAGE, flags=re.S)
        print(preview.replace("<b>", "").replace("</b>", ""))
        print("\n--- кнопки ---")
        for row in KEYBOARD["inline_keyboard"]:
            target = row[0].get("url") or f"внутри бота: {row[0].get('callback_data')}"
            print(f"  [{row[0]['text']}] -> {target}")
        print(f"\nОтправка займёт около {round(len(recipients) * SEND_INTERVAL_SECONDS / 60)} мин.")
        print("Это предпросмотр. Добавьте --send, чтобы отправить.")
        return 0

    # SecretStr renders as "**********" inside an f-string, which Telegram
    # answers with a 404 that reads like a missing chat.
    token = settings.BOT_TOKEN
    token = token.get_secret_value() if hasattr(token, "get_secret_value") else str(token)
    api_base = f"https://api.telegram.org/bot{token}"

    sent = 0
    failures: list[str] = []
    for index, user in enumerate(recipients):
        ok, detail = await send(api_base, user.telegram_id)
        sent += ok
        if not ok:
            failures.append(f"{user.username or user.telegram_id}: {detail}")
        if (index + 1) % 20 == 0:
            print(f"  отправлено {index + 1} из {len(recipients)}…")
        if index + 1 < len(recipients):
            await asyncio.sleep(SEND_INTERVAL_SECONDS)

    print(f"\nИтого: доставлено {sent}, не доставлено {len(failures)}")
    for line in failures[:20]:
        print(f"  {line}")
    if len(failures) > 20:
        print(f"  …и ещё {len(failures) - 20}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
