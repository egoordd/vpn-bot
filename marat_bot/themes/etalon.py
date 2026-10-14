"""Тема etalon — «Etalon VPN» (13.10.2026, бывший «Марат VPN»). Ни слова об основном проекте.

По фирменному листу заказчика: тёмно-синий, золото, слоновая кость, ключ-«E».
Каждый основной экран — баннер (assets/etalon, генератор scripts/make_etalon_banners.py)
с подписью; подпись держится в пределах 1024 знаков (лимит Telegram).
"""
from __future__ import annotations

import os

from marat_bot.core import DEVICES, NAME, PLANS, Access, per_month
from marat_bot.themes.common import COMMAND_LINES, DOC_BUTTONS, FLAGS, TRIAL, TRIAL_GB, Look, card, escape_name, quote

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "etalon")
BANNERS = {
    screen: os.path.join(_ASSETS, f"{file}.jpg")
    for screen, file in {
        "home": "home", "issued": "issued", "connect": "connect", "steps": "connect", "status": "status",
        "tariffs": "tariffs", "checkout": "tariffs", "help": "help", "how": "how", "ref": "ref",
    }.items()
}

LOOK = Look(
    active="✦ <b>Доступ активен</b> · пробный период",
    expired="✕ <b>Доступ закончился</b>",
    limited="◐ <b>Трафик закончился</b>",
    left="⏳ Осталось <b>{left}</b>",
    until="🗓 До {date}",
    was_until="🗓 Был до {date}",
    traffic="📶 {bar} {used} / {limit} ГБ",
    traffic_unlimited="📶 {used} ГБ · без лимита",
    devices="📱 До {devices} устройств",
)

BUTTONS = {
    "trial": f"🔑 Попробовать бесплатно — {TRIAL}",
    "tariffs": "💳 Тарифы",
    "how": "📖 Как это работает",
    "help": "❔ Помощь",
    "support": "💬 Поддержка",
    "link": "🗝 У меня есть подписка",
    "connect": "📲 Подключить устройство",
    "connect_short": "📲 Подключить",
    "me": "👤 Мой доступ",
    "ref": "🤝 Пригласить друга",
    "promo": "🎟 Промокод",
    "review": "⭐️ Отзыв",
    "renew": "🔑 Продлить доступ",
    "renew_short": "🔑 Продлить",
    "news": "📰 Новости",
    "menu": "← Меню",
    "menu_short": "← Меню",
    "to_tariffs": "← Тарифы",
    "pay": "💳 Оплатить",
    "other_device": "← Другое устройство",
    "install": "① Скачать Happ",
    "add": "② Добавить в Happ",
    "dev_ios": "📱 iPhone · iPad",
    "dev_android": "🤖 Android",
    "dev_windows": "🖥 Windows",
    "dev_macos": "💻 Mac",
    "plan": "{label} · {price} ₽",
    "admin": "🛠 Админка",
    **DOC_BUTTONS,
}


def welcome(name: str | None = None) -> str:
    safe = escape_name(name)
    return (
        f"<b>{NAME}</b> — интернет, каким он должен быть.\n\n"
        + (f"Привет, <b>{safe}</b>! " if safe else "Привет! ")
        + "Быстрое и защищённое соединение на телефоне и компьютере — в одно касание.\n\n"
        + quote(
            f"✦ 4 страны: {FLAGS}",
            "✦ <b>Авто-выбор</b> сам держит лучший сервер",
            "✦ <b>Режим РУ-сервисов</b> — банки и Госуслуги без отключения VPN",
        )
        + f"\n\n🔑 <b>{TRIAL} бесплатно</b> · до {DEVICES} устройств · без оплаты"
    )


def issued(until: str) -> str:
    return (
        "🔑 <b>Доступ открыт</b>\n\n"
        + quote(f"⏳ До <b>{until}</b>", f"📱 До {DEVICES} устройств · 📶 {TRIAL_GB} ГБ")
        + "\n\nОсталось подключить устройство — выберите его 👇"
    )


ALREADY = "Пробный доступ уже выдан — он один на аккаунт Telegram."

PICK_DEVICE = "📲 <b>Подключение</b>\n\nНа каком устройстве будете пользоваться VPN? Пришлю короткую инструкцию."

_DEVICE_ICONS = {"iPhone / iPad": "📱", "Android": "🤖", "Windows": "🖥", "macOS": "💻"}


def steps(device: str, link: str) -> str:
    return (
        f"{_DEVICE_ICONS.get(device, '📲')} <b>{device}</b> · три шага\n\n"
        "① Скачайте приложение <b>Happ</b> — первая кнопка ниже\n"
        "② Нажмите «Добавить в Happ» — подписка добавится сама\n"
        "③ Выберите <b>⚡️ Авто-выбор</b> и включите VPN\n\n"
        + quote(
            "<b>Кнопка не сработала?</b>",
            "Нажмите на ссылку — она скопируется. В Happ: «+» → «Вставить из буфера».",
            f"<code>{link}</code>",
            expandable=True,
        )
    )


def status(access: Access, link: str) -> str:
    return (
        "👤 <b>Мой доступ</b>\n\n"
        + quote(*card(access, LOOK))
        + f"\n\n🔗 Ссылка подписки — нажмите, чтобы скопировать:\n<code>{link}</code>"
    )


def home(access: Access | None, name: str | None = None) -> str:
    if access is None:
        return welcome(name)
    if access.active:
        return (
            f"<b>{NAME}</b> · ✦ доступ активен\n\n"
            + quote(*card(access, LOOK)[1:])
            + "\n\n📲 «Подключить устройство» — добавить телефон или компьютер."
        )
    return (
        f"<b>{NAME}</b> · доступ закончился\n\n"
        + quote(*card(access, LOOK)[1:])
        + "\n\n🔑 Продлить — кнопка ниже."
    )


def tariffs() -> str:
    rows = [
        f"✦ <b>{label}</b> — {price} ₽" + (f" · {per_month(days, price)} ₽/мес" if days > 31 else "")
        for days, label, price in PLANS
    ]
    return (
        "💳 <b>Тарифы</b>\n\n"
        + quote(*rows)
        + f"\n\nВ каждом: {FLAGS}, ⚡️ Авто-выбор, 🇷🇺 Режим РУ-сервисов, до 5 устройств.\nВыберите срок 👇"
    )


def checkout(label: str, price: int) -> str:
    return (
        "💳 <b>Оплата</b>\n\n"
        + quote(f"Тариф: <b>{label}</b>", f"К оплате: <b>{price} ₽</b>")
        + "\n\n⏳ Оплата скоро будет подключена.\n"
        f"Пока доступен пробный период — {TRIAL} бесплатно."
    )


def referral(link: str) -> str:
    return (
        "🤝 <b>Пригласить друга</b>\n\n"
        "Отправьте другу ссылку — он получит пробный доступ:\n"
        f"<code>{link}</code>\n\n"
        "⏳ Бонусы за приглашённых друзей скоро появятся."
    )


COMMANDS_GUIDE = quote(*COMMAND_LINES)


def help_text(telegram_id: int) -> str:
    return (
        "❔ <b>Помощь</b>\n\n"
        "<b>Команды</b> — нажмите, чтобы выполнить:\n"
        + COMMANDS_GUIDE
        + "\n\n<b>Режимы в Happ</b>\n"
        + quote(
            "⚡️ <b>Авто-выбор</b> — сам выбирает лучший сервер",
            "🇷🇺 <b>Режим РУ-сервисов</b> — российское открывается напрямую",
            f"{FLAGS} — конкретная страна",
        )
        + "\n\n<b>Если перестало работать</b>\n"
        + quote(
            "1. В Happ потяните список вниз — подписка обновится",
            "2. Выключите и снова включите VPN",
            "3. Выберите другую страну",
            "4. Не помогло — /support",
            expandable=True,
        )
        + f"\n\nВаш ID: <code>{telegram_id}</code>"
    )


HOW_IT_WORKS = (
    "📖 <b>Как это работает</b>\n\n"
    "Приложение шифрует соединение и ведёт его через наши серверы в Европе и США, "
    "а Авто-выбор постоянно держит самый быстрый из них. Российские сервисы "
    "в режиме РУ-сервисов открываются напрямую.\n\n"
    + quote(
        "📲 Приложение Happ — iPhone, Android, Windows, Mac",
        "🔗 Одна ссылка — все страны и режимы сразу",
        f"🔑 Пробный доступ: {TRIAL}, до {DEVICES} устройств, {TRIAL_GB} ГБ",
    )
)

SHORT_DESCRIPTION = f"{NAME} — интернет, каким он должен быть. 🔑 {TRIAL} бесплатно, без оплаты."
DESCRIPTION = (
    f"🔑 {NAME} — интернет, каким он должен быть.\n\n"
    "✦ Быстрое и защищённое соединение\n"
    "✦ 4 страны: Польша, Финляндия, Нидерланды, США\n"
    "✦ Авто-выбор сам держит лучший сервер\n"
    "✦ Банки и Госуслуги работают без отключения VPN\n\n"
    f"Нажмите «Старт» — {TRIAL} бесплатно, до {DEVICES} устройств."
)

STUB_SUPPORT = "💬 Поддержка скоро будет доступна прямо в боте."
STUB_NEWS = "📰 Канал с новостями скоро появится."
STUB_PROMO = "🎟 Промокоды скоро появятся."
STUB_REVIEW = "⭐️ Отзывы скоро можно будет оставить прямо здесь."
STUB_LINK = "🗝 Привязка уже купленной подписки скоро появится."
STUB_PAY = "💳 Оплата скоро будет подключена."
NEED_ACCESS = "Сначала получите пробный доступ — кнопка «🔑 Попробовать бесплатно» в главном меню."
ERROR = "Не получилось — попробуйте ещё раз через минуту."
