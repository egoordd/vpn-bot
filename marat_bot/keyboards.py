"""Клавиатуры бота (словари Bot API). Разделы как в полноценном боте; где действия с нашей стороны нет — заглушки.

Подписи кнопок — из темы (texts.BUTTONS), раскладка общая."""
from __future__ import annotations

import os

from marat_bot import texts
from marat_bot.core import PLANS, Access

SUPPORT_URL = os.environ.get("MARAT_SUPPORT_URL", "").strip()
NEWS_URL = os.environ.get("MARAT_NEWS_URL", "").strip()

APPS = {
    "ios": ("iPhone / iPad", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
    "android": ("Android", "https://play.google.com/store/apps/details?id=com.happproxy"),
    "windows": ("Windows", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"),
    "macos": ("macOS", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg"),
}


def _button(key: str, action: str, style: str | None = None, **fmt: object) -> dict:
    """key — подпись из темы, action — https-ссылка или callback, style — цвет главной кнопки экрана."""
    label = texts.BUTTONS[key].format(**fmt) if fmt else texts.BUTTONS[key]
    button = {"text": label}
    button["url" if action.startswith("https://") else "callback_data"] = action
    if style:
        button["style"] = style
    return button


def _kb(*rows: list[dict]) -> dict:
    return {"inline_keyboard": [list(row) for row in rows]}


def _support() -> dict:
    return _button("support", SUPPORT_URL or "stub:support")


def _news() -> dict:
    return _button("news", NEWS_URL or "stub:news")


def main(access: Access | None, admin: bool = False) -> dict:
    markup = _main(access)
    if admin:
        markup["inline_keyboard"].append([_button("admin", "adm")])
    return markup


def _main(access: Access | None) -> dict:
    if access is None:
        return _kb(
            [_button("trial", "trial", "success")],
            [_button("tariffs", "tariffs"), _button("how", "how")],
            [_button("help", "help"), _support()],
            [_button("link", "stub:link")],
        )
    if access.active:
        return _kb(
            [_button("connect", "connect", "primary")],
            [_button("me", "me"), _button("tariffs", "tariffs")],
            [_button("ref", "ref"), _button("promo", "stub:promo")],
            [_button("help", "help"), _support(), _button("review", "stub:review")],
        )
    return _kb(
        [_button("renew", "tariffs", "success")],
        [_button("me", "me"), _button("promo", "stub:promo")],
        [_button("help", "help"), _support()],
    )


def my_subscription() -> dict:
    return _kb(
        [_button("connect", "connect", "primary")],
        [_button("renew_short", "tariffs", "success")],
        [_button("menu", "menu")],
    )


def tariffs() -> dict:
    rows = [[_button("plan", f"plan:{days}", label=label, price=price)] for days, label, price in PLANS]
    return _kb(*rows, [_button("menu", "menu")])


def checkout() -> dict:
    return _kb(
        [_button("pay", "stub:pay", "primary")],
        [_button("to_tariffs", "tariffs"), _button("menu_short", "menu")],
    )


def devices() -> dict:
    return _kb(
        [_button("dev_ios", "dev:ios"), _button("dev_android", "dev:android")],
        [_button("dev_windows", "dev:windows"), _button("dev_macos", "dev:macos")],
        [_button("menu", "menu")],
    )


def device_steps(store_url: str, happ_url: str) -> dict:
    return _kb(
        [_button("install", store_url)],
        [_button("add", happ_url, "success")],
        [_button("other_device", "connect"), _button("menu_short", "menu")],
    )


def help_menu() -> dict:
    return _kb(
        [_button("connect_short", "connect"), _button("how", "how")],
        [_support(), _news()],
        [_button("menu", "menu")],
    )


def back() -> dict:
    return _kb([_button("menu", "menu")])


def callbacks(markup: dict) -> set[str]:
    """Все callback-кнопки клавиатуры — тест сверяет, что у каждой есть обработчик."""
    return {b["callback_data"] for row in markup["inline_keyboard"] for b in row if "callback_data" in b}
