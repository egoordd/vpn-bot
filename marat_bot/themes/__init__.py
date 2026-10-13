"""Оформление ботов: у каждого заказчика своя тема с одинаковым набором имён.

MARAT_THEME выбирает тему службы: classic — исходная, orbit — «Ярослав VPN»,
etalon — «Etalon VPN» (бывший «Марат VPN»), plata — «Plata VPN» (бывший «Ярослав VPN»);
у etalon и plata баннеры: BANNERS {экран: файл}.
INTERFACE — что обязана определить тема; тест сверяет это для всех тем.
"""
from __future__ import annotations

import importlib
from types import ModuleType

THEMES = ("classic", "orbit", "etalon", "plata")
INTERFACE = (
    "NAME", "TRIAL", "BUTTONS", "welcome", "issued", "ALREADY", "PICK_DEVICE", "steps", "status", "home",
    "tariffs", "checkout", "referral", "COMMANDS_GUIDE", "help_text", "HOW_IT_WORKS", "SHORT_DESCRIPTION",
    "DESCRIPTION", "STUB_SUPPORT", "STUB_NEWS", "STUB_PROMO", "STUB_REVIEW", "STUB_LINK", "STUB_PAY",
    "NEED_ACCESS", "ERROR",
)
BUTTON_KEYS = (
    "trial", "tariffs", "how", "help", "support", "link", "connect", "connect_short", "me", "ref", "promo",
    "review", "renew", "renew_short", "news", "menu", "menu_short", "to_tariffs", "pay", "other_device",
    "install", "add", "dev_ios", "dev_android", "dev_windows", "dev_macos", "plan", "admin",
    "docs", "privacy", "terms", "site_tariffs", "pay_terms", "support_cancel", "support_reply",
)


def load(name: str) -> ModuleType:
    if name not in THEMES:
        raise SystemExit(f"MARAT_THEME: неизвестная тема {name!r}, есть {', '.join(THEMES)}")
    module = importlib.import_module(f"marat_bot.themes.{name}")
    missing = [item for item in INTERFACE if not hasattr(module, item)]
    missing += [f"BUTTONS[{key}]" for key in BUTTON_KEYS if key not in getattr(module, "BUTTONS", {})]
    if missing:
        raise SystemExit(f"тема {name}: нет {', '.join(missing)}")
    return module
