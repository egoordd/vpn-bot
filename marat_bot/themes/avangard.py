"""Тема avangard — «Avangard GT» (13.10.2026). Ни слова об основном проекте.

Гоночный стиль «GT»: графит, карбон, гоночный красный, белые цифры. Серверы — как в
тестовой ссылке заказчика: 🇩🇪 Германия и 🇳🇱 Нидерланды + ⚡️ Авто-обход, без российских
серверов (режима РУ-сервисов нет). Каждый основной экран — баннер (assets/avangard,
генератор scripts/make_avangard_banners.py), подпись в пределах 1024 знаков.
Формулировки нейтральные: про скорость и защиту соединения, без «обхода блокировок».
"""
from __future__ import annotations

import os

from marat_bot.core import DEVICES, NAME, PLANS, Access, per_month
from marat_bot.themes.common import COMMAND_LINES, DOC_BUTTONS, TRIAL, TRIAL_GB, Look, card, escape_name, quote

FLAGS = "🇩🇪 🇳🇱"
COUNTRIES = "Германия и Нидерланды"

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "avangard")
BANNERS = {
    screen: os.path.join(_ASSETS, f"{file}.jpg")
    for screen, file in {
        "home": "home", "issued": "issued", "connect": "connect", "steps": "connect", "status": "status",
        "tariffs": "tariffs", "checkout": "tariffs", "help": "help", "how": "how", "ref": "ref",
    }.items()
}

LOOK = Look(
    active="🟢 <b>На трассе</b> · пробный заезд",
    expired="🔴 <b>Заезд окончен</b> — доступ закончился",
    limited="🟡 <b>Бак пуст</b> — трафик закончился",
    left="⏱ Осталось <b>{left}</b>",
    until="🏁 До {date}",
    was_until="🏁 Был до {date}",
    traffic="⛽️ {bar} {used} / {limit} ГБ",
    traffic_unlimited="⛽️ {used} ГБ · без лимита",
    devices="📱 До {devices} устройств",
    full="▮",
    empty="▯",
)

BUTTONS = {
    "trial": f"🏁 Тест-драйв — {TRIAL} бесплатно",
    "tariffs": "💳 Тарифы",
    "how": "⚙️ Как это работает",
    "help": "🛠 Помощь",
    "support": "💬 Поддержка",
    "link": "🔑 У меня есть подписка",
    "connect": "📲 Подключить устройство",
    "connect_short": "📲 Подключить",
    "me": "📊 Мой доступ",
    "ref": "🤝 Пригласить друга",
    "promo": "🎟 Промокод",
    "review": "⭐️ Отзыв",
    "renew": "🏁 Продлить доступ",
    "renew_short": "🏁 Продлить",
    "news": "📰 Новости",
    "menu": "◂ В гараж",
    "menu_short": "◂ Меню",
    "to_tariffs": "◂ Тарифы",
    "pay": "💳 Оплатить",
    "other_device": "◂ Другое устройство",
    "install": "1 · Скачать Happ",
    "add": "2 · Добавить в Happ",
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
        f"<b>{NAME}</b> — интернет на высокой передаче.\n\n"
        + (f"Привет, <b>{safe}</b>! " if safe else "Привет! ")
        + "Быстрое и защищённое соединение на телефоне и компьютере — в одно касание.\n\n"
        + quote(
            f"▸ Серверы: {FLAGS} {COUNTRIES}",
            "▸ <b>⚡️ Авто-обход</b> сам держит самый быстрый сервер",
            f"▸ До {DEVICES} устройств на одной подписке",
        )
        + f"\n\n🏁 <b>Тест-драйв {TRIAL} бесплатно</b> · без оплаты"
    )


def issued(until: str) -> str:
    return (
        "🏁 <b>Старт дан — доступ открыт</b>\n\n"
        + quote(f"⏱ До <b>{until}</b>", f"📱 До {DEVICES} устройств · ⛽️ {TRIAL_GB} ГБ")
        + "\n\nОсталось подключить устройство — выберите его 👇"
    )


ALREADY = "Тест-драйв уже выдан — он один на аккаунт Telegram."

PICK_DEVICE = "📲 <b>Подключение</b>\n\nНа каком устройстве будете пользоваться VPN? Пришлю короткую инструкцию."

_DEVICE_ICONS = {"iPhone / iPad": "📱", "Android": "🤖", "Windows": "🖥", "macOS": "💻"}


def steps(device: str, link: str) -> str:
    return (
        f"{_DEVICE_ICONS.get(device, '📲')} <b>{device}</b> · три шага до старта\n\n"
        "1 · Скачайте приложение <b>Happ</b> — первая кнопка ниже\n"
        "2 · Нажмите «Добавить в Happ» — подписка добавится сама\n"
        "3 · Выберите <b>⚡️ Авто-обход</b> и включите VPN\n\n"
        + quote(
            "<b>Кнопка не сработала?</b>",
            "Нажмите на ссылку — она скопируется. В Happ: «+» → «Вставить из буфера».",
            f"<code>{link}</code>",
            expandable=True,
        )
    )


def status(access: Access, link: str) -> str:
    return (
        "📊 <b>Мой доступ</b>\n\n"
        + quote(*card(access, LOOK))
        + f"\n\n🔗 Ссылка подписки — нажмите, чтобы скопировать:\n<code>{link}</code>"
    )


def home(access: Access | None, name: str | None = None) -> str:
    if access is None:
        return welcome(name)
    if access.active:
        return (
            f"<b>{NAME}</b> · 🟢 на трассе\n\n"
            + quote(*card(access, LOOK)[1:])
            + "\n\n📲 «Подключить устройство» — добавить телефон или компьютер."
        )
    return (
        f"<b>{NAME}</b> · 🔴 доступ закончился\n\n"
        + quote(*card(access, LOOK)[1:])
        + "\n\n🏁 Продлить — кнопка ниже."
    )


def tariffs() -> str:
    rows = [
        f"▸ <b>{label}</b> — {price} ₽" + (f" · {per_month(days, price)} ₽/мес" if days > 31 else "")
        for days, label, price in PLANS
    ]
    return (
        "💳 <b>Тарифы</b>\n\n"
        + quote(*rows)
        + f"\n\nВ каждом: {FLAGS} {COUNTRIES}, ⚡️ Авто-обход, до 5 устройств.\nВыберите срок 👇"
    )


def checkout(label: str, price: int) -> str:
    return (
        "💳 <b>Оплата</b>\n\n"
        + quote(f"Тариф: <b>{label}</b>", f"К оплате: <b>{price} ₽</b>")
        + "\n\n⏳ Оплата скоро будет подключена.\n"
        f"Пока доступен тест-драйв — {TRIAL} бесплатно."
    )


def referral(link: str) -> str:
    return (
        "🤝 <b>Пригласить друга</b>\n\n"
        "Отправьте другу ссылку — он получит тест-драйв:\n"
        f"<code>{link}</code>\n\n"
        "⏳ Бонусы за приглашённых друзей скоро появятся."
    )


COMMANDS_GUIDE = quote(*COMMAND_LINES)


def help_text(telegram_id: int) -> str:
    return (
        "🛠 <b>Помощь</b>\n\n"
        "<b>Команды</b> — нажмите, чтобы выполнить:\n"
        + COMMANDS_GUIDE
        + "\n\n<b>Режимы в Happ</b>\n"
        + quote(
            "⚡️ <b>Авто-обход</b> — сам выбирает самый быстрый сервер",
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
    "⚙️ <b>Как это работает</b>\n\n"
    "Приложение строит защищённое соединение с нашими серверами в Европе, "
    "а Авто-обход постоянно держит самый быстрый из них.\n\n"
    + quote(
        "📲 Приложение Happ — iPhone, Android, Windows, Mac",
        "🔗 Одна ссылка — все серверы и Авто-обход сразу",
        f"🏁 Тест-драйв: {TRIAL}, до {DEVICES} устройств, {TRIAL_GB} ГБ",
    )
)

SHORT_DESCRIPTION = f"{NAME} — интернет на высокой передаче. 🏁 Тест-драйв {TRIAL} бесплатно."
DESCRIPTION = (
    f"🏁 {NAME} — интернет на высокой передаче.\n\n"
    "▸ Быстрое и защищённое соединение\n"
    f"▸ Серверы: {COUNTRIES}\n"
    "▸ Авто-обход сам держит самый быстрый сервер\n"
    "▸ iPhone, Android, Windows, Mac\n\n"
    f"Нажмите «Старт» — тест-драйв {TRIAL} бесплатно, до {DEVICES} устройств."
)

STUB_SUPPORT = "💬 Поддержка скоро будет доступна прямо в боте."
STUB_NEWS = "📰 Канал с новостями скоро появится."
STUB_PROMO = "🎟 Промокоды скоро появятся."
STUB_REVIEW = "⭐️ Отзывы скоро можно будет оставить прямо здесь."
STUB_LINK = "🔑 Привязка уже купленной подписки скоро появится."
STUB_PAY = "💳 Оплата скоро будет подключена."
NEED_ACCESS = "Сначала возьмите тест-драйв — кнопка «🏁 Тест-драйв» в главном меню."
ERROR = "Не получилось — попробуйте ещё раз через минуту."
