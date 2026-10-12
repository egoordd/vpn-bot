"""Тема orbit — «Ярослав VPN» (12.10.2026). Та же логика, своё лицо.

Отличия от classic: заголовки разделов капсом, слоган курсивом, «тест-драйв»
вместо «пробного доступа», шаги цифрами-эмодзи, трафик кружками ●○, свой
набор иконок и подписей кнопок. Ни слова об основном проекте.
"""
from __future__ import annotations

from marat_bot.core import DEVICES, NAME, PLANS, Access, per_month
from marat_bot.themes.common import COMMAND_LINES, FLAGS, TRIAL, TRIAL_GB, Look, card, escape_name, quote

TAGLINE = "<i>Интернет без границ — в один тап</i>"

LOOK = Look(
    active="✅ <b>Доступ активен</b> · тест-драйв",
    expired="⛔️ <b>Доступ закончился</b>",
    limited="⚠️ <b>Трафик закончился</b>",
    left="⏱ Осталось <b>{left}</b>",
    until="📅 До {date}",
    was_until="📅 Был до {date}",
    traffic="📊 {bar} {used} / {limit} ГБ",
    traffic_unlimited="📊 {used} ГБ · без лимита",
    devices="🖥 До {devices} устройств",
    full="●",
    empty="○",
)

BUTTONS = {
    "trial": f"🚀 Тест-драйв {TRIAL} — бесплатно",
    "tariffs": "💎 Тарифы",
    "how": "🧭 Как это работает",
    "help": "🛟 Помощь",
    "support": "💬 Поддержка",
    "link": "🔑 У меня есть подписка",
    "connect": "🔌 Подключить устройство",
    "connect_short": "🔌 Подключить",
    "me": "👤 Мой доступ",
    "ref": "🤝 Позвать друга",
    "promo": "🏷 Промокод",
    "review": "✍️ Отзыв",
    "renew": "🔄 Продлить доступ",
    "renew_short": "🔄 Продлить",
    "news": "📰 Новости",
    "menu": "↩️ Меню",
    "menu_short": "↩️ Меню",
    "to_tariffs": "↩️ Тарифы",
    "pay": "💳 Оплатить",
    "other_device": "↩️ Другое устройство",
    "install": "1️⃣ Скачать Happ",
    "add": "2️⃣ Добавить в Happ",
    "dev_ios": "📱 iPhone · iPad",
    "dev_android": "🤖 Android",
    "dev_windows": "🪟 Windows",
    "dev_macos": "💻 Mac",
    "plan": "💎 {label} — {price} ₽",
    "admin": "🛠 Админка",
}


def _brand() -> str:
    return f"🛰 <b>{NAME}</b>"


def welcome(name: str | None = None) -> str:
    safe = escape_name(name)
    return (
        f"{_brand()}\n{TAGLINE}\n\n"
        + (f"Привет, <b>{safe}</b>! 👋\n\n" if safe else "Привет! 👋\n\n")
        + "▫️ YouTube, Instagram, ChatGPT — без зависаний\n"
        f"▫️ 4 локации: {FLAGS}\n"
        "▫️ ⚡️ Авто-обход сам держит самый быстрый сервер\n"
        "▫️ 🇷🇺 Банки и Госуслуги работают, VPN выключать не нужно\n\n"
        f"🚀 <b>Тест-драйв {TRIAL} бесплатно</b> — до {DEVICES} устройств, без карты"
    )


def issued(until: str) -> str:
    return (
        "🚀 <b>ТЕСТ-ДРАЙВ ЗАПУЩЕН</b>\n\n"
        + quote(f"⏱ До <b>{until}</b>", f"🖥 До {DEVICES} устройств · 📊 {TRIAL_GB} ГБ")
        + "\n\nТеперь подключите устройство — выберите его 👇"
    )


ALREADY = "Тест-драйв уже запущен — он один на аккаунт Telegram."

PICK_DEVICE = "🔌 <b>ПОДКЛЮЧЕНИЕ</b>\n\nВыберите устройство — инструкция займёт минуту."

_DEVICE_ICONS = {"iPhone / iPad": "📱", "Android": "🤖", "Windows": "🪟", "macOS": "💻"}


def steps(device: str, link: str) -> str:
    return (
        f"{_DEVICE_ICONS.get(device, '🔌')} <b>{device}</b> · подключение за минуту\n\n"
        "1️⃣ Скачайте <b>Happ</b> — первая кнопка ниже\n"
        "2️⃣ Нажмите «Добавить в Happ» — подписка подтянется сама\n"
        "3️⃣ Выберите <b>⚡️ Авто-обход</b> и подключитесь\n\n"
        + quote(
            "🔗 <b>Кнопка не открылась?</b>",
            "Нажмите на ссылку — она скопируется. В Happ: «+» → «Вставить из буфера».",
            f"<code>{link}</code>",
            expandable=True,
        )
    )


def status(access: Access, link: str) -> str:
    return (
        "👤 <b>МОЙ ДОСТУП</b>\n\n"
        + quote(*card(access, LOOK))
        + f"\n\n🔗 Ссылка подписки (нажмите — скопируется):\n<code>{link}</code>"
    )


def home(access: Access | None, name: str | None = None) -> str:
    if access is None:
        return welcome(name)
    if access.active:
        return (
            f"{_brand()} · ✅ доступ активен\n\n"
            + quote(*card(access, LOOK)[1:])
            + "\n\n🔌 «Подключить устройство» — добавить телефон или компьютер."
        )
    return (
        f"{_brand()} · ⛔️ доступ закончился\n\n"
        + quote(*card(access, LOOK)[1:])
        + "\n\n🔄 Продлить — кнопка ниже."
    )


def tariffs() -> str:
    rows = [
        f"🗓 {label} — <b>{price} ₽</b>" + (f" ({per_month(days, price)} ₽/мес)" if days > 31 else "")
        for days, label, price in PLANS
    ]
    return (
        "💎 <b>ТАРИФЫ</b>\n\n"
        + quote(*rows)
        + f"\n\nВсегда включено: {FLAGS} · ⚡️ Авто-обход · 🇷🇺 РУ-режим · до 5 устройств"
    )


def checkout(label: str, price: int) -> str:
    return (
        "💳 <b>ОПЛАТА</b>\n\n"
        + quote(f"🗓 {label}", f"💎 <b>{price} ₽</b>")
        + "\n\n⏳ Оплата появится совсем скоро.\n"
        f"А пока — тест-драйв {TRIAL} бесплатно."
    )


def referral(link: str) -> str:
    return (
        "🤝 <b>ПОЗВАТЬ ДРУГА</b>\n\n"
        "Перешлите другу ссылку — ему достанется тест-драйв:\n"
        f"<code>{link}</code>\n\n"
        "🎁 Бонусы за друзей — скоро."
    )


COMMANDS_GUIDE = quote(*COMMAND_LINES)


def help_text(telegram_id: int) -> str:
    return (
        "🛟 <b>ПОМОЩЬ</b>\n\n"
        "⌨️ <b>Команды</b> — нажмите, чтобы выполнить\n"
        + COMMANDS_GUIDE
        + "\n\n🧭 <b>Режимы в Happ</b>\n"
        + quote(
            "⚡️ Авто-обход — сам выбирает самый быстрый сервер",
            "🇷🇺 Режим РУ-сервисов — российское открывается напрямую",
            f"{FLAGS} — конкретная страна",
        )
        + "\n\n🔧 <b>Не работает?</b>\n"
        + quote(
            "1️⃣ В Happ потяните список вниз — подписка обновится",
            "2️⃣ Отключитесь и подключитесь снова",
            "3️⃣ Выберите другую страну",
            "4️⃣ Всё ещё нет — /support",
            expandable=True,
        )
        + f"\n\n🆔 Ваш ID: <code>{telegram_id}</code>"
    )


HOW_IT_WORKS = (
    "🧭 <b>КАК ЭТО РАБОТАЕТ</b>\n\n"
    "Трафик идёт через наши серверы за границей — сайты видят зарубежный адрес, "
    "и открывается всё, что заблокировано.\n\n"
    + quote(
        "📲 Приложение Happ: iPhone, Android, Windows, Mac",
        "🔗 Одна ссылка — все локации и режимы",
        f"🚀 Тест-драйв: {TRIAL}, до {DEVICES} устройств, {TRIAL_GB} ГБ",
    )
)

SHORT_DESCRIPTION = f"VPN без зависаний: YouTube, Instagram, ChatGPT. 🚀 Тест-драйв {TRIAL} — бесплатно."
DESCRIPTION = (
    f"🛰 {NAME} — интернет без границ в один тап.\n\n"
    "▫️ YouTube, Instagram, ChatGPT — без зависаний\n"
    "▫️ 4 локации: Польша, Финляндия, Нидерланды, США\n"
    "▫️ Авто-обход сам держит самый быстрый сервер\n"
    "▫️ Банки и Госуслуги работают без отключения VPN\n\n"
    f"🚀 Нажмите «Старт» — тест-драйв {TRIAL} бесплатно, без карты."
)

STUB_SUPPORT = "💬 Поддержка появится прямо здесь — совсем скоро."
STUB_NEWS = "📰 Канал с новостями скоро откроется."
STUB_PROMO = "🏷 Промокоды скоро заработают."
STUB_REVIEW = "✍️ Отзывы скоро можно будет оставить прямо тут."
STUB_LINK = "🔑 Привязка уже купленной подписки скоро появится."
STUB_PAY = "💳 Оплата появится совсем скоро."
NEED_ACCESS = "Сначала запустите тест-драйв — кнопка «🚀 Тест-драйв» в меню."
ERROR = "Что-то пошло не так — попробуйте через минуту."
