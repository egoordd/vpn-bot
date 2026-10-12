"""Telegram-часть «Марат VPN»: /start, выдача пробного доступа, подключение, статус."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marat_bot import texts  # noqa: E402
from marat_bot.core import (  # noqa: E402
    INBOUNDS, PROXIES, TRIAL_TRAFFIC_BYTES, Access, Store, happ_link, panel_username, sub_link,
    token_from_url, trial_expire,
)
from services.marzban_client import MarzbanClient, MarzbanNotFoundError  # noqa: E402

log = logging.getLogger("marat_bot")
router = Router()
store = Store(os.environ.get("MARAT_DB", "/var/lib/marat-bot/users.sqlite3"))
_issue_lock = asyncio.Lock()

APPS = {
    "ios": ("iPhone / iPad", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
    "android": ("Android", "https://play.google.com/store/apps/details?id=com.happproxy"),
    "windows": ("Windows", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"),
    "macos": ("macOS", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg"),
}


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """(подпись, callback или https-ссылка) → клавиатура."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=label, url=value) if value.startswith("https://")
            else InlineKeyboardButton(text=label, callback_data=value)
            for label, value in row
        ]
        for row in rows
    ])


MENU = _kb([[("▸ Подключить", "connect"), ("▸ Мой доступ", "me")], [("▸ Как пользоваться", "help")]])
START = _kb([[("◆ Получить доступ бесплатно", "trial")], [("▸ Как это работает", "help")]])
DEVICES_KB = _kb([
    [("iPhone / iPad", "dev:ios"), ("Android", "dev:android")],
    [("Windows", "dev:windows"), ("macOS", "dev:macos")],
    [("‹ Назад", "menu")],
])
BACK = _kb([[("‹ В меню", "menu")]])


async def _access(username: str) -> Access | None:
    try:
        user = await MarzbanClient().get_user(username)
    except MarzbanNotFoundError:
        return None
    return Access(
        username=user.username,
        token=token_from_url(user.subscription_url),
        expire=user.expire,
        status=user.status,
        used_bytes=user.used_traffic_bytes,
        limit_bytes=user.data_limit_bytes,
    )


async def _home(target: Message, telegram_id: int, *, edit: bool = False) -> None:
    username = store.get(telegram_id)
    access = await _access(username) if username else None
    if access and access.token:
        text, kb = texts.status(access, sub_link(access.token)), MENU
    else:
        text, kb = texts.WELCOME, START
    if edit:
        await target.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await _home(message, message.from_user.id)


@router.callback_query(F.data == "menu")
async def on_menu(call: CallbackQuery) -> None:
    await _home(call.message, call.from_user.id, edit=True)
    await call.answer()


@router.callback_query(F.data == "trial")
async def on_trial(call: CallbackQuery) -> None:
    telegram_id = call.from_user.id
    async with _issue_lock:
        existing = store.get(telegram_id)
        # Учётку могли удалить в панели вручную — тогда выдаём заново, а не держим человека на «уже есть».
        if existing and await _access(existing):
            await call.answer(texts.ALREADY, show_alert=True)
            await _home(call.message, telegram_id, edit=True)
            return
        username = panel_username(telegram_id)
        try:
            access = await _access(username)
            if access is None:
                await MarzbanClient().create_user(
                    username=username,
                    expire_at=trial_expire(),
                    data_limit_bytes=TRIAL_TRAFFIC_BYTES,
                    proxies=PROXIES,
                    inbounds=INBOUNDS,
                    note=f"Марат VPN: пробный доступ, tg {telegram_id}",
                )
                access = await _access(username)
        except Exception:
            log.exception("trial issue failed for %s", telegram_id)
            await call.answer(texts.ERROR, show_alert=True)
            return
        store.add(telegram_id, username)
    log.info("trial issued: %s", username)
    await call.message.edit_text(
        texts.ISSUED.format(until=texts.date_msk(access.expire)) if access and access.expire else texts.ISSUED.format(until="—"),
        reply_markup=DEVICES_KB,
    )
    await call.answer()


@router.callback_query(F.data == "connect")
async def on_connect(call: CallbackQuery) -> None:
    await call.message.edit_text(texts.PICK_DEVICE, reply_markup=DEVICES_KB)
    await call.answer()


@router.callback_query(F.data.startswith("dev:"))
async def on_device(call: CallbackQuery) -> None:
    username = store.get(call.from_user.id)
    access = await _access(username) if username else None
    if not access or not access.token:
        await _home(call.message, call.from_user.id, edit=True)
        await call.answer()
        return
    device, store_url = APPS.get(call.data.split(":", 1)[1], APPS["ios"])
    kb = _kb([
        [("1 · Установить Happ", store_url)],
        [("2 · Добавить в Happ", happ_link(access.token))],
        [("‹ Другое устройство", "connect"), ("В меню", "menu")],
    ])
    await call.message.edit_text(texts.steps(device, sub_link(access.token)), reply_markup=kb, disable_web_page_preview=True)
    await call.answer()


@router.callback_query(F.data == "me")
async def on_me(call: CallbackQuery) -> None:
    await _home(call.message, call.from_user.id, edit=True)
    await call.answer()


@router.callback_query(F.data == "help")
async def on_help(call: CallbackQuery) -> None:
    await call.message.edit_text(texts.HELP, reply_markup=BACK)
    await call.answer()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ.get("MARAT_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("MARAT_BOT_TOKEN не задан")
    bot = Bot(token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
