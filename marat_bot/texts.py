"""Тексты «Марат VPN». Ни слова об основном проекте — только этот бот."""
from __future__ import annotations

from marat_bot.core import DEVICES, PLANS, TRIAL_DAYS, Access, date_msk, gb

NAME = "Марат VPN"
LINE = "━━━━━━━━━━━━━━"


def _days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} дня"
    return f"{n} дней"


TRIAL = _days(TRIAL_DAYS)

WELCOME = (
    f"<b>{NAME}</b>\n{LINE}\n"
    "Открывает YouTube, Instagram, ChatGPT и всё, что не грузится без VPN.\n\n"
    "◆ 4 страны: Польша, Финляндия, Нидерланды, США\n"
    "◆ <b>Авто-обход</b> сам держит самый быстрый сервер\n"
    "◆ <b>Режим РУ-сервисов</b>: банки и Госуслуги работают, VPN выключать не нужно\n\n"
    f"Попробуйте бесплатно — <b>{TRIAL}, до {DEVICES} устройств</b>."
)

ISSUED = (
    f"✓ <b>Доступ открыт</b>\n{LINE}\n"
    "Работает до <b>{until}</b>.\n\n"
    "Осталось подключить устройство — выберите его ниже."
)

ALREADY = "Пробный доступ уже выдан — он один на аккаунт Telegram."

PICK_DEVICE = f"<b>📲 Подключение</b>\n{LINE}\nВыберите устройство — пришлю короткую инструкцию."

_STEPS = (
    "<b>{device}</b>\n" + LINE + "\n"
    "<b>1.</b> Установите приложение <b>Happ</b> — кнопка ниже.\n"
    "<b>2.</b> Нажмите «Добавить в Happ» — подписка добавится сама.\n"
    "<b>3.</b> В списке выберите <b>⚡️ Авто-обход</b> и включите VPN.\n\n"
    "Кнопка не сработала? Скопируйте ссылку и в Happ нажмите «+» → «Вставить из буфера»:\n"
    "<code>{link}</code>"
)


def steps(device: str, link: str) -> str:
    return _STEPS.format(device=device, link=link)


def status(access: Access, link: str) -> str:
    if access.active:
        head = "● <b>Подписка активна</b>"
        until = f"до <b>{date_msk(access.expire)}</b>" if access.expire else "без срока"
    else:
        head = "○ <b>Подписка закончилась</b>"
        until = f"была до {date_msk(access.expire)}" if access.expire else "—"
    traffic = (
        f"{gb(access.used_bytes)} из {gb(access.limit_bytes)} ГБ" if access.limit_bytes else f"{gb(access.used_bytes)} ГБ"
    )
    return (
        f"<b>📋 Моя подписка</b>\n{LINE}\n"
        f"{head}\n"
        f"▸ Тариф: пробный, {TRIAL}\n"
        f"▸ Срок: {until}\n"
        f"▸ Трафик: {traffic}\n"
        f"▸ Устройств: до {DEVICES}\n\n"
        f"Ссылка подписки:\n<code>{link}</code>"
    )


def home(access: Access | None) -> str:
    if access is None:
        return WELCOME
    if access.active:
        return (
            f"<b>{NAME}</b>\n{LINE}\n"
            f"● Подписка активна до <b>{date_msk(access.expire)}</b>\n\n"
            "Подключить новое устройство — «Подключить». Срок и трафик — «Моя подписка»."
            if access.expire
            else f"<b>{NAME}</b>\n{LINE}\n● Подписка активна."
        )
    return (
        f"<b>{NAME}</b>\n{LINE}\n"
        "○ Пробный доступ закончился.\n\n"
        "Продление и тарифы — в разделе «Тарифы»."
    )


def tariffs() -> str:
    rows = "\n".join(f"▸ {label} — <b>{price} ₽</b>" for _, label, price in PLANS)
    return (
        f"<b>💳 Тарифы</b>\n{LINE}\n"
        f"{rows}\n\n"
        f"Во всех тарифах: 4 страны, Авто-обход, Режим РУ-сервисов, до 5 устройств.\n"
        "Выберите срок:"
    )


def checkout(label: str, price: int) -> str:
    return (
        f"<b>💳 Оплата</b>\n{LINE}\n"
        f"▸ Тариф: {label}\n"
        f"▸ Стоимость: <b>{price} ₽</b>\n\n"
        "⏳ Оплата скоро будет подключена.\n"
        f"Пока можно бесплатно пользоваться пробным периодом — {TRIAL}."
    )


def referral(link: str) -> str:
    return (
        f"<b>👥 Пригласить друга</b>\n{LINE}\n"
        "Отправьте другу вашу ссылку — он получит пробный доступ.\n\n"
        f"<code>{link}</code>\n\n"
        "⏳ Бонусы за приглашённых друзей скоро появятся."
    )


def help_text(telegram_id: int) -> str:
    return (
        f"<b>❓ Помощь</b>\n{LINE}\n"
        "<b>Как подключиться</b>\n"
        "▸ Получите пробный доступ в главном меню\n"
        "▸ «Подключить» → выберите устройство → «Добавить в Happ»\n"
        "▸ В Happ выберите «⚡️ Авто-обход» и включите VPN\n\n"
        "<b>Режимы</b>\n"
        "▸ <b>⚡️ Авто-обход</b> — сам выбирает самый быстрый сервер\n"
        "▸ <b>🇷🇺 Режим РУ-сервисов</b> — российские сайты и приложения идут напрямую\n"
        "▸ Страны по отдельности — если нужен конкретный сервер\n\n"
        "<b>Если перестало работать</b>\n"
        "▸ в Happ потяните список подписки вниз — она обновится\n"
        "▸ выключите и снова включите VPN\n"
        "▸ попробуйте другую страну\n\n"
        f"Ваш ID: <code>{telegram_id}</code>"
    )


HOW_IT_WORKS = (
    f"<b>ℹ️ Как это работает</b>\n{LINE}\n"
    "Вы подключаетесь к нашим серверам за границей, и сайты видят зарубежный адрес — "
    "поэтому открывается всё, что заблокировано.\n\n"
    "▸ Подключение через приложение Happ — iPhone, Android, Windows, macOS\n"
    "▸ Одна ссылка — все страны и режимы сразу\n"
    f"▸ Пробный доступ бесплатный: {TRIAL}, до {DEVICES} устройств"
)

STUB_SUPPORT = "💬 Поддержка скоро будет доступна прямо в боте."
STUB_NEWS = "📣 Канал с новостями скоро появится."
STUB_PROMO = "🎟 Промокоды скоро появятся."
STUB_REVIEW = "⭐️ Отзывы скоро можно будет оставить прямо здесь."
STUB_LINK = "🔗 Привязка подписки, купленной на сайте, скоро появится."
NEED_ACCESS = "Сначала получите пробный доступ — кнопка в главном меню."
ERROR = "Не получилось — попробуйте ещё раз через минуту."
