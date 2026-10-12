"""Клавиатуры «Марат VPN» (словари Bot API). Разделы как в полноценном боте; где действия с нашей стороны нет — заглушки."""
from __future__ import annotations

import os

from marat_bot.core import PLANS, Access
from marat_bot.texts import TRIAL

SUPPORT_URL = os.environ.get("MARAT_SUPPORT_URL", "").strip()
NEWS_URL = os.environ.get("MARAT_NEWS_URL", "").strip()

APPS = {
    "ios": ("iPhone / iPad", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
    "android": ("Android", "https://play.google.com/store/apps/details?id=com.happproxy"),
    "windows": ("Windows", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"),
    "macos": ("macOS", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg"),
}


def _button(label: str, action: str, style: str | None = None) -> dict:
    """action — https-ссылка или callback. style — цвет главной кнопки экрана."""
    button = {"text": label}
    button["url" if action.startswith("https://") else "callback_data"] = action
    if style:
        button["style"] = style
    return button


def _kb(*rows: list[dict]) -> dict:
    return {"inline_keyboard": [list(row) for row in rows]}


def _support() -> dict:
    return _button("💬 Поддержка", SUPPORT_URL or "stub:support")


def _news() -> dict:
    return _button("📣 Новости", NEWS_URL or "stub:news")


def main(access: Access | None) -> dict:
    if access is None:
        return _kb(
            [_button(f"🎁 Пробный доступ — {TRIAL} бесплатно", "trial", "success")],
            [_button("💳 Тарифы", "tariffs", "primary")],
            [_button("🔗 У меня уже есть подписка", "stub:link")],
            [_button("❓ Помощь", "help"), _support()],
            [_button("ℹ️ Как это работает", "how"), _news()],
        )
    if access.active:
        return _kb(
            [_button("📲 Подключить", "connect", "primary"), _button("📋 Моя подписка", "me")],
            [_button("💳 Тарифы", "tariffs"), _button("👥 Пригласить друга", "ref")],
            [_button("🎟 Промокод", "stub:promo"), _button("⭐️ Отзыв", "stub:review")],
            [_button("❓ Помощь", "help"), _support()],
        )
    return _kb(
        [_button("♻️ Продлить", "tariffs", "success")],
        [_button("📋 Моя подписка", "me"), _button("🎟 Промокод", "stub:promo")],
        [_button("❓ Помощь", "help"), _support()],
    )


def my_subscription() -> dict:
    return _kb(
        [_button("📲 Подключить устройство", "connect", "primary")],
        [_button("♻️ Продлить", "tariffs", "success")],
        [_button("◀️ В меню", "menu")],
    )


def tariffs() -> dict:
    rows = [[_button(f"▸ {label} · {price} ₽", f"plan:{days}")] for days, label, price in PLANS]
    return _kb(*rows, [_button("◀️ В меню", "menu")])


def checkout() -> dict:
    return _kb(
        [_button("💳 Оплатить картой", "stub:pay", "primary")],
        [_button("◀️ К тарифам", "tariffs"), _button("В меню", "menu")],
    )


def devices() -> dict:
    return _kb(
        [_button("📱 iPhone / iPad", "dev:ios"), _button("🤖 Android", "dev:android")],
        [_button("💻 Windows", "dev:windows"), _button("🍏 macOS", "dev:macos")],
        [_button("◀️ В меню", "menu")],
    )


def device_steps(store_url: str, happ_url: str) -> dict:
    return _kb(
        [_button("1 · Установить Happ", store_url)],
        [_button("2 · Добавить в Happ", happ_url, "success")],
        [_button("◀️ Другое устройство", "connect"), _button("В меню", "menu")],
    )


def help_menu() -> dict:
    return _kb([_support(), _news()], [_button("◀️ В меню", "menu")])


def back() -> dict:
    return _kb([_button("◀️ В меню", "menu")])


def callbacks(markup: dict) -> set[str]:
    """Все callback-кнопки клавиатуры — тест сверяет, что у каждой есть обработчик."""
    return {b["callback_data"] for row in markup["inline_keyboard"] for b in row if "callback_data" in b}
