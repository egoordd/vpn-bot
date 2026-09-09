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
from pathlib import Path
from datetime import datetime, timezone

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import Subscription, User


CHANNEL_POST_URL = "https://t.me/UnlockAccess/51"

# Every delivery is written down the moment it succeeds. A broadcast is a
# long job over a link that can drop, and without a ledger a resumed run has
# no way to tell who already heard from us — so it would tell everyone twice.
LEDGER = Path("/opt/vpn-bot/var/broadcast_block_sent.txt")

# Telegram tolerates ~30 messages/second; one every 1.5s stays far inside that
# and keeps a stalled send from cascading.
SEND_INTERVAL_SECONDS = 1.5

MESSAGE = (
    f'🚫 <b><a href="{CHANNEL_POST_URL}">РКН заблокировал наш сайт. '
    "Переезжаем на новый</a></b>\n\n"
    "Прежний адрес перестал открываться у части операторов связи. "
    "Новый сайт работает здесь: <b>unlockproject.site</b>\n\n"
    "<b>Подписки пока работают на прежнем адресе</b> — ссылку в приложении менять "
    "не нужно, удалять тоже. Переносить их на новый домен будем постепенно. Когда "
    "дойдёт очередь до вашей, вам придёт уведомление: сюда, в бота, или на почту — "
    "таким же сообщением.\n\n"
    "<b>Такое будет повторяться.</b> Адреса блокируют, мы переезжаем на новые. "
    "Чтобы не потерять с нами связь, подпишитесь на наш канал: там мы сразу "
    "публикуем новый адрес, предупреждаем о работах и выкладываем промокоды.\n\n"
    "📣 @UnlockAccess\n\n"
    "Если сайт не открывается, пропали серверы или не выходит подключить "
    "устройство — напишите нам. Поможем и компенсируем потерянное время.\n"
    "Поддержка: @unlock_support_bot\n"
    "Почта, если Telegram недоступен: unlockvpnru@gmail.com"
)

KEYBOARD = {
    "inline_keyboard": [
        [{"text": "📣 Подписаться на канал", "url": "https://t.me/UnlockAccess"}],
        [{"text": "🌐 Новый сайт", "url": "https://unlockproject.site"}],
        [{"text": "💬 Написать в поддержку", "url": "https://t.me/unlock_support_bot"}],
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


def already_delivered(ledger: Path) -> set[int]:
    if not ledger.exists():
        return set()
    ids = set()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.isdigit() or (line.startswith("-") and line[1:].isdigit()):
            ids.add(int(line))
    return ids


def record(ledger: Path, chat_id: int) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(f"{chat_id}\n")
        fh.flush()


async def send(api_base: str, chat_id: int) -> tuple[bool, str]:
    payload = {
        "chat_id": chat_id,
        "text": MESSAGE,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
        "reply_markup": KEYBOARD,
    }
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as http:
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
    parser.add_argument(
        "--state",
        default=str(LEDGER),
        help="файл с уже доставленными id; повтор запуска их пропустит",
    )
    args = parser.parse_args()
    ledger = Path(args.state)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_pool() as session:
            recipients = await load_recipients(
                session, args.audience, args.telegram_ids or None
            )
    finally:
        await engine.dispose()

    delivered = already_delivered(ledger)
    if delivered:
        before = len(recipients)
        recipients = [u for u in recipients if u.telegram_id not in delivered]
        print(f"Уже получили в прошлый раз: {before - len(recipients)} — пропускаю их.")

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
        if ok:
            record(ledger, user.telegram_id)
        else:
            failures.append(f"{user.username or user.telegram_id}: {detail}")
        if (index + 1) % 20 == 0:
            print(f"  отправлено {index + 1} из {len(recipients)}…", flush=True)
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
