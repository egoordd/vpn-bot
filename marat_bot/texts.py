"""Тексты «Марат VPN». Ни слова об основном проекте — только этот бот.

Оформление без картинок: карточки — цитаты Telegram (<blockquote>), длинное
прячется в раскрывающуюся цитату, трафик — полоской ▰▱.
"""
from __future__ import annotations

import html

from marat_bot.core import (
    DEVICES, PLANS, TRIAL_DAYS, TRIAL_TRAFFIC_BYTES, Access, bar, date_msk, days_word, gb, per_month, time_left,
)

NAME = "Марат VPN"
FLAGS = "🇵🇱 🇫🇮 🇳🇱 🇺🇸"
TRIAL = days_word(TRIAL_DAYS)
TRIAL_GB = TRIAL_TRAFFIC_BYTES // 1024**3


def _quote(*lines: str, expandable: bool = False) -> str:
    tag = "blockquote expandable" if expandable else "blockquote"
    return f"<{tag}>" + "\n".join(lines) + "</blockquote>"


def _hello(name: str | None) -> str:
    return f"👋 <b>Привет, {html.escape(name)}!</b>" if name else "👋 <b>Привет!</b>"


def welcome(name: str | None = None) -> str:
    return (
        f"{_hello(name)}\n\n"
        f"<b>{NAME}</b> — быстрый VPN для YouTube, Instagram, ChatGPT и всего, что не открывается.\n\n"
        + _quote(
            f"🌍 4 страны: {FLAGS}",
            "⚡️ <b>Авто-обход</b> — сам держит самый быстрый сервер",
            "🇷🇺 <b>Режим РУ-сервисов</b> — банки и Госуслуги работают без отключения VPN",
        )
        + f"\n\n🎁 <b>{TRIAL} бесплатно</b> · до {DEVICES} устройств · без оплаты"
    )


def issued(until: str) -> str:
    return (
        "🎉 <b>Доступ открыт!</b>\n\n"
        + _quote(f"⏳ До <b>{until}</b>", f"📱 До {DEVICES} устройств · 📶 {TRIAL_GB} ГБ")
        + "\n\nОсталось подключить устройство — выберите его 👇"
    )


ALREADY = "Пробный доступ уже выдан — он один на аккаунт Telegram."

PICK_DEVICE = "📲 <b>Подключение</b>\n\nНа каком устройстве будете пользоваться VPN? Пришлю короткую инструкцию."

_DEVICE_ICONS = {"iPhone / iPad": "📱", "Android": "🤖", "Windows": "💻", "macOS": "🍏"}


def steps(device: str, link: str) -> str:
    return (
        f"{_DEVICE_ICONS.get(device, '📲')} <b>{device}</b> — 3 шага\n\n"
        "<b>1</b> · Установите приложение <b>Happ</b> — кнопка «1 · Установить Happ»\n"
        "<b>2</b> · Нажмите «2 · Добавить в Happ» — подписка добавится сама\n"
        "<b>3</b> · Выберите <b>⚡️ Авто-обход</b> и включите VPN\n\n"
        + _quote(
            "<b>Кнопка не сработала?</b>",
            "Нажмите на ссылку — она скопируется. В Happ: «+» → «Вставить из буфера».",
            f"<code>{link}</code>",
            expandable=True,
        )
    )


def _traffic(access: Access) -> str:
    if not access.limit_bytes:
        return f"📶 Трафик: {gb(access.used_bytes)} ГБ"
    return f"📶 {bar(access.used_bytes, access.limit_bytes)} {gb(access.used_bytes)} из {gb(access.limit_bytes)} ГБ"


def _card(access: Access) -> list[str]:
    if access.active:
        lines = ["🟢 <b>Активна</b> · пробный период"]
        if access.expire:
            lines += [f"⏳ Осталось: <b>{time_left(access.expire)}</b>", f"🗓 До {date_msk(access.expire)}"]
    else:
        lines = ["🔴 <b>Подписка закончилась</b>"]
        if access.expire:
            lines.append(f"🗓 Была до {date_msk(access.expire)}")
    return [*lines, _traffic(access), f"📱 Устройств: до {DEVICES}"]


def status(access: Access, link: str) -> str:
    return (
        "📋 <b>Моя подписка</b>\n\n"
        + _quote(*_card(access))
        + f"\n\n🔗 Ссылка подписки — нажмите, чтобы скопировать:\n<code>{link}</code>"
    )


def home(access: Access | None, name: str | None = None) -> str:
    if access is None:
        return welcome(name)
    if access.active:
        return (
            f"<b>{NAME}</b> · 🟢 доступ активен\n\n"
            + _quote(*_card(access)[1:])
            + "\n\n📲 «Подключить» — добавить телефон или компьютер."
        )
    return (
        f"<b>{NAME}</b> · 🔴 доступ закончился\n\n"
        + _quote(*_card(access)[1:])
        + "\n\n♻️ Продлить — кнопка ниже."
    )


def tariffs() -> str:
    rows = [
        f"<b>{label}</b> — {price} ₽" + (f" · {per_month(days, price)} ₽/мес" if days > 31 else "")
        for days, label, price in PLANS
    ]
    return (
        "💳 <b>Тарифы</b>\n\n"
        + _quote(*rows)
        + f"\n\nВо всех тарифах: {FLAGS}, ⚡️ Авто-обход, 🇷🇺 Режим РУ-сервисов, до 5 устройств.\n"
        "Выберите срок 👇"
    )


def checkout(label: str, price: int) -> str:
    return (
        "💳 <b>Оплата</b>\n\n"
        + _quote(f"Тариф: <b>{label}</b>", f"К оплате: <b>{price} ₽</b>")
        + "\n\n⏳ Оплата скоро будет подключена.\n"
        f"Пока можно пользоваться пробным периодом — {TRIAL} бесплатно."
    )


def referral(link: str) -> str:
    return (
        "👥 <b>Пригласить друга</b>\n\n"
        "Отправьте другу ссылку — он получит пробный доступ:\n"
        f"<code>{link}</code>\n\n"
        "⏳ Бонусы за приглашённых друзей скоро появятся."
    )


COMMANDS_GUIDE = _quote(
    "/start — главное меню",
    "/connect — подключить устройство",
    "/status — срок, трафик и ссылка подписки",
    "/tariffs — тарифы",
    "/promo — ввести промокод",
    "/support — поддержка",
    "/help — эта справка",
)


def help_text(telegram_id: int) -> str:
    return (
        "❓ <b>Помощь</b>\n\n"
        "<b>Команды</b> — нажмите, чтобы выполнить:\n"
        + COMMANDS_GUIDE
        + "\n\n<b>Режимы в Happ</b>\n"
        + _quote(
            "⚡️ <b>Авто-обход</b> — сам выбирает самый быстрый сервер",
            "🇷🇺 <b>Режим РУ-сервисов</b> — российские сайты и приложения идут напрямую",
            f"{FLAGS} — конкретная страна, если нужна именно она",
        )
        + "\n\n<b>Если перестало работать</b>\n"
        + _quote(
            "1. В Happ потяните список вниз — подписка обновится",
            "2. Выключите и снова включите VPN",
            "3. Выберите другую страну",
            "4. Не помогло — /support",
            expandable=True,
        )
        + f"\n\nВаш ID: <code>{telegram_id}</code>"
    )


HOW_IT_WORKS = (
    "ℹ️ <b>Как это работает</b>\n\n"
    "Вы подключаетесь к серверам за границей, и сайты видят зарубежный адрес — "
    "поэтому открывается всё, что заблокировано.\n\n"
    + _quote(
        "📲 Приложение Happ — iPhone, Android, Windows, macOS",
        "🔗 Одна ссылка — все страны и режимы сразу",
        f"🎁 Пробный доступ: {TRIAL}, до {DEVICES} устройств, {TRIAL_GB} ГБ",
    )
)

SHORT_DESCRIPTION = f"Быстрый VPN для YouTube, Instagram и ChatGPT. 🎁 {TRIAL} бесплатно, без оплаты."
DESCRIPTION = (
    f"⚡️ {NAME} — быстрый VPN для YouTube, Instagram, ChatGPT и всего, что не открывается.\n\n"
    "🌍 4 страны: Польша, Финляндия, Нидерланды, США\n"
    "⚡️ Авто-обход сам выбирает самый быстрый сервер\n"
    "🇷🇺 Банки и Госуслуги работают без отключения VPN\n\n"
    f"🎁 Нажмите «Старт» — {TRIAL} бесплатно, до {DEVICES} устройств."
)

STUB_SUPPORT = "💬 Поддержка скоро будет доступна прямо в боте."
STUB_NEWS = "📣 Канал с новостями скоро появится."
STUB_PROMO = "🎟 Промокоды скоро появятся."
STUB_REVIEW = "⭐️ Отзывы скоро можно будет оставить прямо здесь."
STUB_LINK = "🔗 Привязка подписки, купленной на сайте, скоро появится."
NEED_ACCESS = "Сначала получите пробный доступ — кнопка «🎁 Попробовать бесплатно» в главном меню."
ERROR = "Не получилось — попробуйте ещё раз через минуту."
