"""Рассылка о повышении цен с 26.09.2026 — в основной бот и в зеркало.

По умолчанию только предпросмотр: кому и что уйдёт. Отправка — с --send.

    .venv/bin/python scripts/broadcast_price_rise.py --bot main
    .venv/bin/python scripts/broadcast_price_rise.py --bot main --send

Зеркало берёт свой токен из /etc/unlock-mirror.env:

    set -a; . /etc/unlock-mirror.env; set +a
    .venv/bin/python scripts/broadcast_price_rise.py --bot mirror --send

Перед отправкой скрипт спрашивает у Telegram, чей это токен, и останавливается,
если бот не тот: письмо зеркала не должно уйти от основного бота и наоборот.
Каждая доставка записывается сразу, поэтому повторный запуск после обрыва
никому не пишет дважды.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import User

# Как в services/mirror_bot.py: аккаунт зеркала хранится под этим сдвигом.
MIRROR_ID_OFFSET = 9_000_000_000_000_000
SEND_INTERVAL_SECONDS = 1.5

BOTS = {
    # Кнопка ведёт в меню покупки: у основного бота это buy_menu, у зеркала —
    # экран тарифов с кнопками оплаты.
    "main": {"username": "unlkvpn_bot", "heart": "💙", "callback": "buy_menu"},
    "mirror": {"username": "UnLockFreedom_bot", "heart": "💛", "callback": "tariffs"},
}


def message(heart: str) -> str:
    return (
        "📈 <b>Через 3 дня цены вырастут</b>\n\n"
        "Нас становится всё больше, и мы усиливаем серверы, чтобы VPN работал "
        "стабильнее. Поэтому с 26 сентября подписка будет стоить:\n\n"
        "• 1 месяц — <s>149 ₽</s> → <b>199 ₽</b>\n"
        "• 3 месяца — <s>399 ₽</s> → <b>549 ₽</b>\n"
        "• 6 месяцев — <s>699 ₽</s> → <b>999 ₽</b>\n"
        "• 12 месяцев — <s>1 199 ₽</s> → <b>1 799 ₽</b>\n\n"
        "⏳ <b>Последний шанс купить по старой цене — до конца 25 сентября "
        "(по Москве).</b> Оформите или продлите подписку сейчас, и весь оплаченный "
        "срок будет по текущей цене. Если подписка уже есть, новый срок добавится "
        "к оставшимся дням и ничего не сгорит.\n\n"
        f"Спасибо, что остаётесь с UnLock {heart}"
    )


def keyboard(callback: str) -> dict:
    return {"inline_keyboard": [[{"text": "💳 Купить по старой цене", "callback_data": callback}]]}


async def load_chats(bot: str) -> list[int]:
    """Чаты получателей: у основного бота — положительные id, у зеркала — его аккаунты."""

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    try:
        async with async_sessionmaker(engine)() as session:
            if bot == "main":
                query = select(User.telegram_id).where(User.telegram_id > 0)
            else:
                query = select(User.telegram_id).where(User.telegram_id <= -MIRROR_ID_OFFSET)
            ids = list((await session.execute(query.order_by(User.id))).scalars())
    finally:
        await engine.dispose()
    if bot == "mirror":
        ids = [-account - MIRROR_ID_OFFSET for account in ids]
    return list(dict.fromkeys(ids))


def delivered(ledger: Path) -> set[int]:
    if not ledger.exists():
        return set()
    return {int(line) for line in ledger.read_text().split() if line.lstrip("-").isdigit()}


def record(ledger: Path, chat_id: int) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(f"{chat_id}\n")


async def call(http: aiohttp.ClientSession, api: str, method: str, payload: dict | None = None) -> dict:
    async with http.post(f"{api}/{method}", json=payload or {}) as response:
        return await response.json(content_type=None)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bot", choices=tuple(BOTS), required=True)
    parser.add_argument("--send", action="store_true", help="отправить (иначе только показать)")
    parser.add_argument("chat_ids", nargs="*", type=int, help="только этим чатам (проверка)")
    args = parser.parse_args()

    config = BOTS[args.bot]
    text = message(config["heart"])
    markup = keyboard(config["callback"])
    ledger = Path(f"/opt/vpn-bot/var/broadcast_price_rise_{args.bot}.txt")

    chats = args.chat_ids or await load_chats(args.bot)
    done = delivered(ledger)
    pending = [chat for chat in chats if chat not in done]
    print(f"Бот: @{config['username']}  |  всего {len(chats)}, уже получили {len(chats) - len(pending)}, "
          f"осталось {len(pending)}")

    if not args.send:
        print("\n--- текст ---\n" + text.replace("<b>", "").replace("</b>", "")
              .replace("<s>", "~").replace("</s>", "~"))
        print(f"\n[💳 Купить по старой цене] → {config['callback']}")
        print("\nЭто предпросмотр. Добавьте --send, чтобы отправить.")
        return 0

    token = settings.BOT_TOKEN
    token = token.get_secret_value() if hasattr(token, "get_secret_value") else str(token)
    api = f"https://api.telegram.org/bot{token}"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        me = await call(http, api, "getMe")
        username = (me.get("result") or {}).get("username", "")
        if username.lower() != config["username"].lower():
            print(f"СТОП: токен принадлежит @{username or '?'}, а рассылка для @{config['username']}.")
            return 2

        sent, failures = 0, []
        for index, chat in enumerate(pending):
            try:
                body = await call(http, api, "sendMessage", {
                    "chat_id": chat,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                    "reply_markup": markup,
                })
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                body = {"ok": False, "description": f"сеть: {exc}"}
            if body.get("ok"):
                sent += 1
                record(ledger, chat)
            else:
                failures.append(f"{chat}: {body.get('description')}")
            if (index + 1) % 20 == 0:
                print(f"  {index + 1} из {len(pending)}…", flush=True)
            if index + 1 < len(pending):
                await asyncio.sleep(SEND_INTERVAL_SECONDS)

    print(f"\nИтого: доставлено {sent}, не доставлено {len(failures)}")
    for line in failures[:30]:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
