"""«Марат VPN»: меню, пробный доступ, подключение, тарифы и разделы-заглушки (Bot API напрямую)."""
from __future__ import annotations

import asyncio
import functools
import html
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marat_bot import admin  # noqa: E402
from marat_bot import keyboards as kb  # noqa: E402
from marat_bot import texts  # noqa: E402
from marat_bot.core import (  # noqa: E402
    INBOUNDS, NAME, PLANS, PROXIES, TRIAL_TRAFFIC_BYTES, Access, Store, date_msk, happ_link, panel_username, sub_link,
    token_from_url, trial_expire,
)
from marat_bot.tg import TelegramError, Tg  # noqa: E402

log = logging.getLogger("marat_bot")
_issue_lock = asyncio.Lock()
_bot_username = ""

STUBS = {
    "support": texts.STUB_SUPPORT,
    "news": texts.STUB_NEWS,
    "promo": texts.STUB_PROMO,
    "review": texts.STUB_REVIEW,
    "link": texts.STUB_LINK,
    "pay": texts.STUB_PAY,
}
CAPTION_LIMIT = 1024
COMMANDS = [
    {"command": "start", "description": "🏠 Главное меню"},
    {"command": "connect", "description": "📲 Подключить устройство"},
    {"command": "status", "description": "📋 Срок, трафик и ссылка подписки"},
    {"command": "tariffs", "description": "💳 Тарифы"},
    {"command": "promo", "description": "🎟 Промокод"},
    {"command": "support", "description": "💬 Поддержка"},
    {"command": "help", "description": "❓ Помощь и все команды"},
]
# Конфетти поверх сообщения «Доступ открыт» (эффекты Telegram работают в личных чатах).
EFFECT_PARTY = "5046509860389126442"
HANDLED = {"menu", "trial", "me", "connect", "tariffs", "help", "how", "ref", "adm"}
HANDLED_PREFIXES = ("dev:", "plan:", "stub:", "adm:")


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
                proxies=PROXIES, inbounds=INBOUNDS, note=f"{NAME}: пробный доступ, tg {telegram_id}",
            )
            access = await _access(username)
        _store().add(telegram_id, username)
        log.info("trial issued: %s", username)
        return access, True


def _banner(screen: str | None, text: str) -> str | None:
    """Картинка экрана, если у темы она есть и подпись влезает в лимит Telegram."""
    path = texts.BANNERS.get(screen or "")
    if not path:
        return None
    visible = html.unescape(re.sub(r"<[^>]+>", "", text))
    return path if len(visible.encode("utf-16-le")) // 2 <= CAPTION_LIMIT else None


async def send_screen(tg: Tg, chat: int, screen: str | None, text: str, markup: dict | None = None,
                      effect: str | None = None) -> None:
    banner = _banner(screen, text)
    if banner:
        try:
            await tg.send_photo(chat, banner, text, markup, effect=effect)
            return
        except Exception:
            log.exception("banner %s failed, sending text", screen)
    await tg.send(chat, text, markup, effect=effect)


async def edit_screen(tg: Tg, chat: int, msg: int, screen: str | None, text: str, markup: dict | None = None) -> None:
    """Поменять экран на месте. Картинку нельзя превратить в текст и наоборот —
    тогда новый экран приходит отдельным сообщением, а старое удаляется."""
    banner = _banner(screen, text)
    try:
        if banner:
            await tg.edit_media(chat, msg, banner, text, markup)
        else:
            await tg.edit(chat, msg, text, markup)
        return
    except TelegramError as exc:
        log.info("screen %s: edit failed (%s), sending anew", screen, exc)
    await send_screen(tg, chat, screen, text, markup)
    await tg.delete(chat, msg)


async def on_message(tg: Tg, message: dict) -> None:
    text = (message.get("text") or "").strip()
    chat = message["chat"]["id"]
    sender = message.get("from", {})
    user = sender.get("id", chat)
    words = text.split()
    command = words[0].split("@")[0].lower() if text.startswith("/") else ""
    store = _store()
    store.touch(user, sender.get("username"), sender.get("first_name"))
    is_admin = admin.is_admin(store, sender)
    if is_admin and command in ("/start", "/admin"):
        await admin.set_menu(tg, chat, COMMANDS)
    if is_admin and command in admin.COMMANDS:
        client, not_found = _panel()
        try:
            await admin.handle(tg, chat, command, words[1:], store, client, not_found)
        except Exception:
            log.exception("admin command %s failed", command)
            await tg.send(chat, texts.ERROR)
        return
    if command == "/help":
        await send_screen(tg, chat, "help", texts.help_text(user), kb.help_menu())
    elif command == "/promo":
        await tg.send(chat, texts.STUB_PROMO, kb.back())
    elif command == "/support":
        await tg.send(chat, texts.STUB_SUPPORT if not kb.SUPPORT_URL else "💬 Поддержка:", kb.help_menu())
    elif command == "/tariffs":
        await send_screen(tg, chat, "tariffs", texts.tariffs(), kb.tariffs())
    elif command in ("/connect", "/status", "/me"):
        access = await _my_access(user)
        if not access:
            await tg.send(chat, texts.NEED_ACCESS, kb.main(None))
        elif command == "/connect":
            await send_screen(tg, chat, "connect", texts.PICK_DEVICE, kb.devices())
        else:
            await send_screen(tg, chat, "status", texts.status(access, sub_link(access.token)), kb.my_subscription())
    else:
        access = await _my_access(user)
        await send_screen(tg, chat, "home", texts.home(access, sender.get("first_name")), kb.main(access, is_admin))


async def on_callback(tg: Tg, call: dict) -> None:
    data = call.get("data") or ""
    user = call["from"]["id"]
    name = call["from"].get("first_name")
    chat = call["message"]["chat"]["id"]
    msg = call["message"]["message_id"]

    async def show(text: str, markup: dict, screen: str | None = None) -> None:
        await edit_screen(tg, chat, msg, screen, text, markup)
        await tg.answer(call["id"])

    async def alert(text: str) -> None:
        await tg.answer(call["id"], text, alert=True)

    if data == "adm" or data.startswith("adm:"):
        if not admin.is_admin(_store(), call["from"]):
            await tg.answer(call["id"])
            return
        client, _ = _panel()
        try:
            text = await (admin.users_text if data == "adm:users" else admin.panel_text)(_store(), client)
        except Exception:
            log.exception("admin screen %s failed", data)
            await alert(texts.ERROR)
            return
        await show(text, admin.keyboard())
    elif data == "menu":
        access = await _my_access(user)
        await show(texts.home(access, name), kb.main(access, admin.is_admin(_store(), call["from"])), "home")
    elif data == "trial":
        try:
            access, issued = await _issue_trial(user)
        except Exception:
            log.exception("trial issue failed for %s", user)
            await alert(texts.ERROR)
            return
        if not issued:
            await alert(texts.ALREADY)
            await edit_screen(tg, chat, msg, "home", texts.home(access, name), kb.main(access, admin.is_admin(_store(), call["from"])))
            return
        until = date_msk(access.expire) if access and access.expire else "—"
        _store().touch(user, call["from"].get("username"), name)
        # Меню обновляется на «доступ активен», а выдача приходит отдельным сообщением с конфетти.
        await show(texts.home(access, name), kb.main(access, admin.is_admin(_store(), call["from"])), "home")
        await send_screen(tg, chat, "issued", texts.issued(until), kb.devices(), effect=EFFECT_PARTY)
    elif data in ("me", "connect") or data.startswith("dev:"):
        access = await _my_access(user)
        if not access:
            await alert(texts.NEED_ACCESS)
        elif data == "me":
            await show(texts.status(access, sub_link(access.token)), kb.my_subscription(), "status")
        elif data == "connect":
            await show(texts.PICK_DEVICE, kb.devices(), "connect")
        else:
            device, store_url = kb.APPS.get(data.split(":", 1)[1], kb.APPS["ios"])
            await show(texts.steps(device, sub_link(access.token)), kb.device_steps(store_url, happ_link(access.token)),
                       "steps")
    elif data == "tariffs":
        await show(texts.tariffs(), kb.tariffs(), "tariffs")
    elif data.startswith("plan:"):
        plan = next(((label, price) for d, label, price in PLANS if f"plan:{d}" == data), None)
        if plan:
            await show(texts.checkout(*plan), kb.checkout(), "checkout")
        else:
            await tg.answer(call["id"])
    elif data == "help":
        await show(texts.help_text(user), kb.help_menu(), "help")
    elif data == "how":
        await show(texts.HOW_IT_WORKS, kb.back(), "how")
    elif data == "ref":
        link = f"https://t.me/{_bot_username}?start=ref{user}" if _bot_username else "—"
        await show(texts.referral(link), kb.back(), "ref")
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
    for method, field, value in (("setMyName", "name", NAME),
                                 ("setMyShortDescription", "short_description", texts.SHORT_DESCRIPTION),
                                 ("setMyDescription", "description", texts.DESCRIPTION)):
        try:
            await tg.call(method, **{field: value})
        except Exception:
            log.exception("%s failed", method)
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
