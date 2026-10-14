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
from marat_bot import docs  # noqa: E402
from marat_bot import i18n  # noqa: E402
from marat_bot import keyboards as kb  # noqa: E402
from marat_bot import support  # noqa: E402
from marat_bot import webapp  # noqa: E402
from marat_bot import texts  # noqa: E402
from marat_bot.core import (  # noqa: E402
    INBOUNDS, NAME, PLANS, PROXIES, TRIAL_TRAFFIC_BYTES, Access, Store, date_msk, happ_link, panel_username, sub_link,
    token_from_url, trial_expire,
)
from marat_bot.tg import TelegramError, Tg  # noqa: E402

log = logging.getLogger("marat_bot")
_issue_lock = asyncio.Lock()
_bot_username = ""

# Заглушки разделов: текст — из набора текстов человека (у многоязычной темы — на его языке).
STUBS = {key: f"STUB_{key.upper()}" for key in ("support", "news", "promo", "review", "link", "pay")}
CAPTION_LIMIT = 1024
COMMANDS = [
    {"command": "start", "description": "🏠 Главное меню"},
    {"command": "connect", "description": "📲 Подключить устройство"},
    {"command": "status", "description": "📋 Срок, трафик и ссылка подписки"},
    {"command": "tariffs", "description": "💳 Тарифы"},
    {"command": "promo", "description": "🎟 Промокод"},
    {"command": "support", "description": "💬 Поддержка"},
    {"command": "help", "description": "❓ Помощь и все команды"},
] + ([{"command": "language", "description": "🌐 Язык"}] if texts.LANGUAGES else [])
# Конфетти поверх сообщения «Доступ открыт» (эффекты Telegram работают в личных чатах).
EFFECT_PARTY = "5046509860389126442"
HANDLED = {"menu", "trial", "me", "connect", "tariffs", "help", "how", "ref", "adm", "support", "docs", "lang"}
HANDLED_PREFIXES = ("dev:", "plan:", "stub:", "adm:", "lang:")


def _lang(user: int, sender: dict) -> str:
    """Выбранный человеком язык, а пока не выбрал — догадка по настройкам Telegram."""
    return _store().lang(user) or i18n.guess(sender.get("language_code"))


@functools.lru_cache(maxsize=1)
def _store() -> Store:
    return Store(os.environ.get("MARAT_DB", "/var/lib/marat-bot/users.sqlite3"))


PANEL_URL = os.environ.get("MARAT_PANEL_URL", "").strip()


def _panel():
    from services.marzban_client import MarzbanClient, MarzbanNotFoundError

    if PANEL_URL:
        # Свой Marzban заказчика (Avangard VPN): логин его админа из окружения службы.
        client = MarzbanClient(PANEL_URL, username=os.environ.get("MARAT_PANEL_USERNAME", ""),
                               password=os.environ.get("MARAT_PANEL_PASSWORD", ""))
        return client, MarzbanNotFoundError
    # Иначе — наша панель, доступы основного бота из /opt/vpn-bot/.env.
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
    path = getattr(texts.current(), "BANNERS", texts.BANNERS).get(screen or "")
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


async def _support_prompt(tg: Tg, chat: int, user: int) -> None:
    """Открыть обращение в поддержку (команда, кнопка или ссылка ?start=support с сайта)."""
    if kb.SUPPORT_URL:
        await tg.send(chat, "💬 Поддержка:", kb.help_menu())
    elif support.available(_store()):
        support.open_window(user)
        await tg.send(chat, support.msg("PROMPT"), kb.support_prompt())
    else:
        await tg.send(chat, texts.current().STUB_SUPPORT, kb.help_menu())


async def on_message(tg: Tg, message: dict) -> None:
    text = (message.get("text") or "").strip()
    chat = message["chat"]["id"]
    sender = message.get("from", {})
    user = sender.get("id", chat)
    words = text.split()
    command = words[0].split("@")[0].lower() if text.startswith("/") else ""
    store = _store()
    store.touch(user, sender.get("username"), sender.get("first_name"))
    t = texts.use(_lang(user, sender))
    is_admin = admin.is_admin(store, sender)
    if is_admin and not command and message.get("reply_to_message"):
        if await support.reply(tg, store, message, kb.support_answer):
            return
    if command == "/support" or (command == "/start" and words[1:2] == ["support"]):
        await _support_prompt(tg, chat, user)
        return
    if command:
        support.close(user)
    elif chat == user and support.is_open(user):
        await tg.send(chat, await support.forward(tg, store, message))
        return
    if is_admin and command in ("/start", "/admin"):
        await admin.set_menu(tg, chat, COMMANDS)
    if is_admin and command in admin.COMMANDS:
        client, not_found = _panel()
        try:
            await admin.handle(tg, chat, command, words[1:], store, client, not_found)
        except Exception:
            log.exception("admin command %s failed", command)
            await tg.send(chat, t.ERROR)
        return
    if texts.LANGUAGES and (command == "/language" or (command == "/start" and store.lang(user) is None)):
        # Приглашение с выбором языка — при первом /start; «Назад» только когда открыт из меню.
        await send_screen(tg, chat, "lang", t.LANG_PROMPT, kb.languages(_lang(user, sender), back=command == "/language"))
    elif command == "/help":
        await send_screen(tg, chat, "help", t.help_text(user), kb.help_menu())
    elif command == "/promo":
        await tg.send(chat, t.STUB_PROMO, kb.back())
    elif command == "/tariffs":
        await send_screen(tg, chat, "tariffs", t.tariffs(), kb.tariffs())
    elif command in ("/connect", "/status", "/me"):
        access = await _my_access(user)
        if not access:
            await tg.send(chat, t.NEED_ACCESS, kb.main(None))
        elif command == "/connect":
            await send_screen(tg, chat, "connect", t.PICK_DEVICE, kb.devices())
        else:
            await send_screen(tg, chat, "status", t.status(access, sub_link(access.token)), kb.my_subscription())
    else:
        access = await _my_access(user)
        await send_screen(tg, chat, "home", t.home(access, sender.get("first_name")), kb.main(access, is_admin))


async def on_callback(tg: Tg, call: dict) -> None:
    data = call.get("data") or ""
    user = call["from"]["id"]
    name = call["from"].get("first_name")
    chat = call["message"]["chat"]["id"]
    msg = call["message"]["message_id"]

    t = texts.use(_lang(user, call["from"]))

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
            await alert(t.ERROR)
            return
        await show(text, admin.keyboard())
    elif data == "menu":
        support.close(user)
        access = await _my_access(user)
        await show(t.home(access, name), kb.main(access, admin.is_admin(_store(), call["from"])), "home")
    elif data == "trial":
        try:
            access, issued = await _issue_trial(user)
        except Exception:
            log.exception("trial issue failed for %s", user)
            await alert(t.ERROR)
            return
        if not issued:
            await alert(t.ALREADY)
            await edit_screen(tg, chat, msg, "home", t.home(access, name), kb.main(access, admin.is_admin(_store(), call["from"])))
            return
        until = getattr(t, "date_text", date_msk)(access.expire) if access and access.expire else "—"
        _store().touch(user, call["from"].get("username"), name)
        # Меню обновляется на «доступ активен», а выдача приходит отдельным сообщением с конфетти.
        await show(t.home(access, name), kb.main(access, admin.is_admin(_store(), call["from"])), "home")
        await send_screen(tg, chat, "issued", t.issued(until), kb.devices(), effect=EFFECT_PARTY)
    elif data in ("me", "connect") or data.startswith("dev:"):
        access = await _my_access(user)
        if not access:
            await alert(t.NEED_ACCESS)
        elif data == "me":
            await show(t.status(access, sub_link(access.token)), kb.my_subscription(), "status")
        elif data == "connect":
            await show(t.PICK_DEVICE, kb.devices(), "connect")
        else:
            device, store_url = kb.APPS.get(data.split(":", 1)[1], kb.APPS["ios"])
            await show(t.steps(device, sub_link(access.token)), kb.device_steps(store_url, happ_link(access.token)),
                       "steps")
    elif data == "tariffs":
        await show(t.tariffs(), kb.tariffs(), "tariffs")
    elif data.startswith("plan:"):
        plan = next(((kb.plan_label(d, label), price) for d, label, price in PLANS if f"plan:{d}" == data), None)
        if plan:
            await show(t.checkout(*plan) + docs.checkout_note(), kb.checkout(), "checkout")
        else:
            await tg.answer(call["id"])
    elif data == "help":
        await show(t.help_text(user), kb.help_menu(), "help")
    elif data == "how":
        await show(t.HOW_IT_WORKS, kb.back(), "how")
    elif data == "ref":
        link = f"https://t.me/{_bot_username}?start=ref{user}" if _bot_username else "—"
        await show(t.referral(link), kb.back(), "ref")
    elif data == "support":
        if not support.available(_store()):
            await alert(t.STUB_SUPPORT)
            return
        support.open_window(user)
        await show(support.msg("PROMPT"), kb.support_prompt())
    elif data == "docs":
        if not docs.links():
            await tg.answer(call["id"])
            return
        await show(docs.screen_text(), kb.docs_menu())
    elif texts.LANGUAGES and data == "lang":
        await show(t.LANG_PROMPT, kb.languages(_lang(user, call["from"]), back=True), "lang")
    elif texts.LANGUAGES and data.startswith("lang:"):
        code = data.split(":", 1)[1]
        if code not in texts.LANGUAGES:
            await tg.answer(call["id"])
            return
        _store().set_lang(user, code)
        t = texts.use(code)
        flag, language = texts.LANGUAGES[code]
        # Как в приглашении: сообщение с выбором становится «язык установлен» (с кнопкой сменить,
        # если нажал не тот), меню — отдельным сообщением.
        await show(t.LANG_SET.format(language=f"{flag} {language}"), kb.language_set(), "lang")
        access = await _my_access(user)
        await send_screen(tg, chat, "home", t.home(access, name), kb.main(access, admin.is_admin(_store(), call["from"])))
    elif data.startswith("stub:"):
        stub = STUBS.get(data.split(":", 1)[1])
        await alert(getattr(t, stub) if stub else "Скоро появится.")
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


WEBAPP_PORT = int(os.environ.get("MARAT_WEBAPP_PORT", "0") or 0)
WEBAPP_PREFIX = os.environ.get("MARAT_WEBAPP_PREFIX", "/mapp/app")


async def _start_webapp(tg: Tg, token: str) -> None:
    """Mini App: сервер страницы и API в этом же процессе + кнопка «Открыть VPN» у поля ввода."""
    if not WEBAPP_PORT:
        return
    application = webapp.make_app(
        prefix=WEBAPP_PREFIX, bot_token=token, bot_username=lambda: _bot_username, my_access=_my_access,
        issue_trial=_issue_trial, support_available=lambda: support.available(_store()),
    )
    await webapp.start(application, WEBAPP_PORT)
    if kb.WEBAPP_URL.startswith("https://"):
        try:
            await tg.call("setChatMenuButton", menu_button={
                "type": "web_app", "text": "Открыть VPN", "web_app": {"url": kb.WEBAPP_URL},
            })
        except Exception:
            log.exception("setChatMenuButton failed")


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
    # Многоязычная тема: меню команд и описание бота — на языке приложения Telegram у человека.
    for code in texts.LANGUAGES:
        if code == "ru":
            continue
        local = texts.localized(code)
        try:
            await tg.call("setMyCommands", language_code=code, commands=[
                {"command": c["command"], "description": local.COMMAND_MENU.get(c["command"], c["description"])}
                for c in COMMANDS
            ])
            await tg.call("setMyShortDescription", language_code=code, short_description=local.SHORT_DESCRIPTION)
            await tg.call("setMyDescription", language_code=code, description=local.DESCRIPTION)
        except Exception:
            log.exception("localized profile for %s failed", code)
    await _start_webapp(tg, token)
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
