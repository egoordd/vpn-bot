"""«Марат VPN»: меню, пробный доступ, подключение, тарифы и разделы-заглушки (Bot API напрямую)."""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marat_bot import keyboards as kb  # noqa: E402
from marat_bot import texts  # noqa: E402
from marat_bot.core import (  # noqa: E402
    INBOUNDS, PLANS, PROXIES, TRIAL_TRAFFIC_BYTES, Access, Store, happ_link, panel_username, sub_link,
    token_from_url, trial_expire,
)
from marat_bot.tg import Tg  # noqa: E402

log = logging.getLogger("marat_bot")
_issue_lock = asyncio.Lock()
_bot_username = ""

STUBS = {
    "support": texts.STUB_SUPPORT,
    "news": texts.STUB_NEWS,
    "promo": texts.STUB_PROMO,
    "review": texts.STUB_REVIEW,
    "link": texts.STUB_LINK,
    "pay": "💳 Оплата скоро будет подключена.",
}
COMMANDS = [
    {"command": "start", "description": "Главное меню"},
    {"command": "help", "description": "Помощь"},
    {"command": "promo", "description": "Промокод"},
    {"command": "support", "description": "Поддержка"},
]
HANDLED = {"menu", "trial", "me", "connect", "tariffs", "help", "how", "ref"}
HANDLED_PREFIXES = ("dev:", "plan:", "stub:")


@functools.lru_cache(maxsize=1)
def _store() -> Store:
    return Store(os.environ.get("MARAT_DB", "/var/lib/marat-bot/users.sqlite3"))


def _panel():
    # Панель — через клиент основного бота (те же доступы из /opt/vpn-bot/.env).
    from services.marzban_client import MarzbanClient, MarzbanNotFoundError

    return MarzbanClient(), MarzbanNotFoundError


async def _access(username: str | None) -> Access | None:
    if not username:
        return None
    client, not_found = _panel()
    try:
        user = await client.get_user(username)
    except not_found:
        return None
    return Access(
        username=user.username, token=token_from_url(user.subscription_url), expire=user.expire,
        status=user.status, used_bytes=user.used_traffic_bytes, limit_bytes=user.data_limit_bytes,
    )


async def _my_access(telegram_id: int) -> Access | None:
    access = await _access(_store().get(telegram_id))
    return access if access and access.token else None


async def _issue_trial(telegram_id: int) -> tuple[Access | None, bool]:
    """(доступ, выдан ли сейчас). Один пробник на аккаунт Telegram."""
    async with _issue_lock:
        existing = _store().get(telegram_id)
        # Учётку могли удалить в панели вручную — тогда выдаём заново, а не держим человека на «уже есть».
        current = await _access(existing) if existing else None
        if current:
            return current, False
        username = panel_username(telegram_id)
        access = await _access(username)
        if access is None:
            client, _ = _panel()
            await client.create_user(
                username=username, expire_at=trial_expire(), data_limit_bytes=TRIAL_TRAFFIC_BYTES,
                proxies=PROXIES, inbounds=INBOUNDS, note=f"Марат VPN: пробный доступ, tg {telegram_id}",
            )
            access = await _access(username)
        _store().add(telegram_id, username)
        log.info("trial issued: %s", username)
        return access, True


async def on_message(tg: Tg, message: dict) -> None:
    text = (message.get("text") or "").strip()
    chat = message["chat"]["id"]
    user = message.get("from", {}).get("id", chat)
    command = text.split()[0].split("@")[0] if text.startswith("/") else ""
    if command == "/help":
        await tg.send(chat, texts.help_text(user), kb.help_menu())
    elif command == "/promo":
        await tg.send(chat, texts.STUB_PROMO, kb.back())
    elif command == "/support":
        await tg.send(chat, texts.STUB_SUPPORT if not kb.SUPPORT_URL else "💬 Поддержка:", kb.help_menu())
    else:
        access = await _my_access(user)
        await tg.send(chat, texts.home(access), kb.main(access))


async def on_callback(tg: Tg, call: dict) -> None:
    data = call.get("data") or ""
    user = call["from"]["id"]
    chat = call["message"]["chat"]["id"]
    msg = call["message"]["message_id"]

    async def show(text: str, markup: dict) -> None:
        await tg.edit(chat, msg, text, markup)
        await tg.answer(call["id"])

    async def alert(text: str) -> None:
        await tg.answer(call["id"], text, alert=True)

    if data == "menu":
        access = await _my_access(user)
        await show(texts.home(access), kb.main(access))
    elif data == "trial":
        try:
            access, issued = await _issue_trial(user)
        except Exception:
            log.exception("trial issue failed for %s", user)
            await alert(texts.ERROR)
            return
        if not issued:
            await alert(texts.ALREADY)
            await tg.edit(chat, msg, texts.home(access), kb.main(access))
            return
        until = texts.date_msk(access.expire) if access and access.expire else "—"
        await show(texts.ISSUED.format(until=until), kb.devices())
    elif data in ("me", "connect") or data.startswith("dev:"):
        access = await _my_access(user)
        if not access:
            await alert(texts.NEED_ACCESS)
        elif data == "me":
            await show(texts.status(access, sub_link(access.token)), kb.my_subscription())
        elif data == "connect":
            await show(texts.PICK_DEVICE, kb.devices())
        else:
            device, store_url = kb.APPS.get(data.split(":", 1)[1], kb.APPS["ios"])
            await show(texts.steps(device, sub_link(access.token)), kb.device_steps(store_url, happ_link(access.token)))
    elif data == "tariffs":
        await show(texts.tariffs(), kb.tariffs())
    elif data.startswith("plan:"):
        plan = next(((label, price) for d, label, price in PLANS if f"plan:{d}" == data), None)
        if plan:
            await show(texts.checkout(*plan), kb.checkout())
        else:
            await tg.answer(call["id"])
    elif data == "help":
        await show(texts.help_text(user), kb.help_menu())
    elif data == "how":
        await show(texts.HOW_IT_WORKS, kb.back())
    elif data == "ref":
        link = f"https://t.me/{_bot_username}?start=ref{user}" if _bot_username else "—"
        await show(texts.referral(link), kb.back())
    elif data.startswith("stub:"):
        await alert(STUBS.get(data.split(":", 1)[1], "Скоро появится."))
    else:
        await tg.answer(call["id"])


async def _handle(tg: Tg, update: dict) -> None:
    try:
        if "callback_query" in update:
            await on_callback(tg, update["callback_query"])
        elif "message" in update:
            await on_message(tg, update["message"])
    except Exception:
        log.exception("update %s failed", update.get("update_id"))


async def main() -> None:
    global _bot_username
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ.get("MARAT_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("MARAT_BOT_TOKEN не задан")
    tg = Tg(token)
    me = await tg.call("getMe")
    _bot_username = me.get("username", "")
    await tg.call("setMyCommands", commands=COMMANDS)
    await tg.call("deleteWebhook")
    log.info("polling as @%s", _bot_username)
    offset = None
    while True:
        try:
            updates = await tg.updates(offset)
        except Exception:
            log.exception("getUpdates failed")
            await asyncio.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            asyncio.create_task(_handle(tg, update))


if __name__ == "__main__":
    asyncio.run(main())
