"""User-facing legal documents and the tariff sheet for the mirror bot.

The acquirer's bank reviews the bot before the payment desk is registered, and
it wants four things permanently reachable from the interface: a privacy
policy, a user agreement, a support contact that is not a group chat, and the
prices the customer actually pays.  All four live here so the mirror can render
them without reaching for the website.

Nothing in this module is imported by the primary bot.  It is deliberately
self-contained: the mirror must stay clean regardless of what the site or the
main bot say.

Telegram rejects a message body over 4096 characters, and every document is
rendered as a single edited message, so ``check_document_lengths`` guards that
ceiling and the test suite calls it.
"""

from __future__ import annotations

from services.tariffs import TARIFFS, Tariff


# Shown to the acquirer's reviewer while a payment desk is being approved: in
# the bot name and on the help screen. Empty once the desk is registered —
# Platega's was, on 11 September 2026.
VERIFICATION_CODE = ""

PROJECT_NAME = "UnLock VPN"
DOCUMENT_REVISION = "8 сентября 2026 года"

TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_NAME_LIMIT = 64


def bot_display_name() -> str:
    """Name shown in chat lists, carrying the review code while one is set.

    The acquirer asked for the code somewhere obvious, and the bot name is the
    first thing their reviewer sees.  Clearing ``VERIFICATION_CODE`` drops it
    from the name, the help screen and everywhere else at once.
    """

    name = f"{PROJECT_NAME} {VERIFICATION_CODE}".strip() if VERIFICATION_CODE else PROJECT_NAME
    if len(name) > TELEGRAM_NAME_LIMIT:
        raise RuntimeError(
            f"Bot name {name!r} exceeds the {TELEGRAM_NAME_LIMIT}-character limit"
        )
    return name


def _support() -> str:
    """Support handle, read late so the environment stays authoritative."""

    from config import settings

    return settings.support_contact


def privacy_policy() -> str:
    return (
        "🔒 <b>Политика конфиденциальности</b>\n"
        f"<i>Редакция от {DOCUMENT_REVISION}</i>\n\n"
        "<b>1. Общие положения</b>\n"
        f"Политика определяет порядок обработки и защиты данных пользователей сервиса "
        f"{PROJECT_NAME} (далее — Сервис), доступ к которому предоставляется через "
        "Telegram-бота. Используя Сервис, пользователь соглашается с настоящей Политикой.\n\n"
        "<b>2. Какие данные обрабатываются</b>\n"
        "<blockquote>"
        "• идентификатор и имя учётной записи Telegram;\n"
        "• сведения о подписке: тариф, даты начала и окончания, объём переданных "
        "данных, число подключённых устройств;\n"
        "• сведения о платежах: сумма, дата, статус и номер операции, которые "
        "передаёт платёжный сервис."
        "</blockquote>\n"
        "Паспортные данные, адрес проживания и иные сведения, не требующиеся для "
        "оказания услуги, Сервис не запрашивает.\n\n"
        "<b>3. Что Сервис не собирает</b>\n"
        "Сервис не ведёт журналы посещённых пользователем адресов, не хранит "
        "содержимое передаваемых данных, историю запросов DNS и сведения о действиях "
        "пользователя в сети. Фиксируются только объём переданных данных и статус "
        "подключения, нужные для расчёта по тарифу.\n\n"
        "<b>4. Цели обработки</b>\n"
        "<blockquote>"
        "• предоставление и продление доступа к Сервису;\n"
        "• техническая поддержка пользователей;\n"
        "• расчёты за услугу и выполнение требований налогового учёта;\n"
        "• поддержание работоспособности и безопасности инфраструктуры."
        "</blockquote>\n"
        "<b>5. Правовые основания</b>\n"
        "Обработка ведётся с согласия пользователя, а также для исполнения договора, "
        "стороной которого пользователь является.\n\n"
        "<b>6. Передача третьим лицам</b>\n"
        "Данные не передаются третьим лицам, кроме двух случаев: платёжным сервисам — "
        "в объёме, который нужен для проведения расчётов, и уполномоченным органам — в "
        "порядке, предусмотренном законодательством Российской Федерации.\n\n"
        "<b>7. Срок хранения</b>\n"
        "Данные учётной записи хранятся, пока действует подписка, и три года после её "
        "окончания. Сведения о платежах хранятся в сроки, установленные "
        "законодательством.\n\n"
        "<b>8. Защита данных</b>\n"
        "Применяются организационные и технические меры: шифрование каналов связи, "
        "разграничение доступа к серверам, регулярное резервное копирование.\n\n"
        "<b>9. Права пользователя</b>\n"
        "Пользователь вправе запросить сведения об обработке своих данных, потребовать "
        "их уточнения или удаления и отозвать согласие на обработку. Запрос "
        "направляется в поддержку, ответ даётся в течение 30 дней.\n\n"
        "<b>10. Изменение Политики</b>\n"
        "Действующая редакция всегда доступна в этом боте: раздел «ℹ️ О сервисе» → "
        "«🔒 Конфиденциальность», или команда /privacy.\n\n"
        "<b>11. Контакты</b>\n"
        f"Поддержка: {_support()}"
    )


def terms_of_use() -> str:
    return (
        "📄 <b>Пользовательское соглашение</b>\n"
        f"<i>Редакция от {DOCUMENT_REVISION}</i>\n\n"
        "<b>1. Термины</b>\n"
        f"Сервис — {PROJECT_NAME}, программно-аппаратный комплекс, предоставляющий "
        "доступ к защищённому каналу передачи данных (VPN).\n"
        "Пользователь — физическое лицо, использующее Сервис через Telegram-бота.\n"
        "Подписка — право пользования Сервисом в течение оплаченного срока.\n\n"
        "<b>2. Предмет соглашения</b>\n"
        "Сервис предоставляет пользователю платный доступ к защищённому каналу "
        "передачи данных. Назначение Сервиса — обеспечение конфиденциальности "
        "соединения и защита передаваемых данных при работе в публичных и "
        "недоверенных сетях.\n\n"
        "<b>3. Порядок предоставления</b>\n"
        "После оформления подписки пользователь получает персональную ссылку для "
        "настройки клиентского приложения. Ссылка предназначена для личного "
        "использования и не подлежит передаче третьим лицам.\n\n"
        "<b>4. Стоимость и оплата</b>\n"
        "Действующие тарифы приведены в боте в разделе «💳 Тарифы». Оплата вносится "
        "авансом за выбранный период. Подписка активируется автоматически после "
        "подтверждения платежа.\n\n"
        "<b>5. Пробный период</b>\n"
        "Новому пользователю предоставляется бесплатный пробный доступ. Он даётся "
        "однократно, его условия указаны в разделе «Тарифы».\n\n"
        "<b>6. Возврат средств</b>\n"
        "Пользователь вправе отказаться от услуги и потребовать возврат за "
        "неиспользованный период, направив запрос в поддержку. Возврат производится в "
        "течение 10 рабочих дней тем же способом, которым была внесена оплата. "
        "Средства за использованный период возврату не подлежат.\n\n"
        "<b>7. Правила использования</b>\n"
        "Пользователю запрещается применять Сервис для действий, противоречащих "
        "законодательству Российской Федерации, в том числе для рассылки нежелательных "
        "сообщений, распространения вредоносных программ, получения "
        "несанкционированного доступа к чужим информационным системам и нарушения прав "
        "третьих лиц. При выявлении таких действий доступ прекращается без возврата "
        "средств.\n\n"
        "<b>8. Права и обязанности сторон</b>\n"
        "Сервис поддерживает работоспособность инфраструктуры и оказывает техническую "
        "поддержку, а также вправе проводить плановые технические работы, предупреждая "
        "пользователей заранее, когда это возможно.\n"
        "Пользователь сохраняет персональную ссылку в тайне и самостоятельно "
        "обеспечивает сохранность своей учётной записи Telegram.\n\n"
        "<b>9. Пределы ответственности</b>\n"
        "Сервис не отвечает за качество связи, предоставляемой оператором пользователя, "
        "за работу стороннего клиентского программного обеспечения и за последствия "
        "действий, совершённых пользователем при использовании Сервиса.\n\n"
        "<b>10. Изменение условий</b>\n"
        "Сервис вправе изменять условия соглашения. Действующая редакция всегда "
        "доступна в разделе «ℹ️ О сервисе» → «📄 Соглашение» или по команде /terms. "
        "Продолжение использования "
        "Сервиса означает согласие с изменениями.\n\n"
        "<b>11. Контакты</b>\n"
        f"Поддержка: {_support()}"
    )


def _plural(count: int, one: str, few: str, many: str) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return many
    if count % 10 == 1:
        return one
    if 2 <= count % 10 <= 4:
        return few
    return many


def months(tariff: Tariff) -> int:
    """Whole months a paid plan covers: 30, 90, 180 and 365 days read as 1, 3, 6 and 12."""

    return max(1, round(tariff.duration_days / 30.4))


def period_label(tariff: Tariff, *, short: bool = False) -> str:
    count = months(tariff)
    if short:
        return f"{count} мес"
    return f"{count} {_plural(count, 'месяц', 'месяца', 'месяцев')}"


def _per_month(tariff: Tariff) -> int:
    # Rounded half up: 699 ₽ over 6 months reads as 117, not banker's 116.
    return int(tariff.price_rub / months(tariff) + 0.5)


def _paid_tariffs() -> list[Tariff]:
    ordered = sorted(TARIFFS.values(), key=lambda item: item.sort_order)
    return [item for item in ordered if item.price_rub > 0]


def device_limit() -> int | None:
    """Devices a paid plan allows, when every plan allows the same number."""

    limits = {item.device_limit for item in _paid_tariffs()}
    return limits.pop() if len(limits) == 1 else None


def starting_price() -> int | None:
    """The price a subscription starts at: the cheapest plan as it is sold, not a per-month average."""

    prices = [item.price_rub for item in _paid_tariffs()]
    return min(prices) if prices else None


def largest_monthly_traffic_gb() -> int | None:
    volumes = [item.traffic_gb for item in _paid_tariffs() if item.traffic_gb and item.traffic_resets_monthly]
    return max(volumes) if volumes else None


def _traffic(tariff: Tariff) -> str:
    if tariff.traffic_gb is None:
        return "трафик без учёта"
    return f"{tariff.traffic_gb} ГБ " + ("в месяц" if tariff.traffic_resets_monthly else "на весь срок")


def _tariff_line(tariff: Tariff) -> str:
    price = f"{period_label(tariff)} — <b>{tariff.price_rub} ₽</b>"
    if months(tariff) > 1:
        price += f" ({_per_month(tariff)} ₽/мес)"
    details = [_traffic(tariff)]
    if device_limit() is None:
        devices = tariff.device_limit if tariff.device_limit is not None else "∞"
        details.append(f"до {devices} устройств")
    return f"{price}\n<i>{', '.join(details)}</i>"


def _trial() -> Tariff | None:
    return next((item for item in TARIFFS.values() if item.price_rub == 0), None)


def _trial_line() -> str | None:
    trial = _trial()
    if trial is None:
        return None
    days = trial.duration_days
    parts = [f"{days} {_plural(days, 'день', 'дня', 'дней')}"]
    if trial.traffic_gb is not None:
        parts.append(f"{trial.traffic_gb} ГБ")
    if trial.device_limit is not None:
        count = trial.device_limit
        parts.append(f"{count} {_plural(count, 'устройство', 'устройства', 'устройств')}")
    return "🎁 Пробный период: " + ", ".join(parts) + " — один раз для нового пользователя."


def tariffs_text() -> str:
    sections = ["💳 <b>Тарифы</b>", "\n\n".join(_tariff_line(item) for item in _paid_tariffs())]
    notes = []
    devices = device_limit()
    if devices is not None:
        notes.append(f"📱 На любом тарифе — до {devices} {_plural(devices, 'устройства', 'устройств', 'устройств')}.")
    trial = _trial_line()
    if trial:
        notes.append(trial)
    if notes:
        sections.append("<blockquote>" + "\n".join(notes) + "</blockquote>")
    sections.append(
        "Оплата картой или через СБП, авансом за выбранный срок. Подписка включается "
        "сама после оплаты. Условия возврата — в пользовательском соглашении."
    )
    return "\n\n".join(sections)


def bot_description() -> str:
    """The «Что умеет этот бот?» card a newcomer sees before pressing Start."""

    devices = device_limit()
    trial = _trial()
    lines = [
        f"{PROJECT_NAME} — быстрый защищённый VPN для телефона и компьютера.",
        "",
        "⚡️ Подключение одной кнопкой",
        "🌍 Серверы в Европе и США",
    ]
    if devices is not None:
        lines.append(f"📱 До {devices} {_plural(devices, 'устройства', 'устройств', 'устройств')} на подписке")
    if trial is not None:
        days = trial.duration_days
        lines.append(f"🎁 {days} {_plural(days, 'день', 'дня', 'дней')} бесплатно для новых пользователей")
    lines += [
        "",
        "Оплата картой или через СБП. Пользовательское соглашение и политика "
        "конфиденциальности — в разделе «ℹ️ О сервисе».",
    ]
    return "\n".join(lines)


def bot_short_description() -> str:
    return "Быстрый защищённый VPN для телефона и компьютера. Попробуйте бесплатно."


def documents() -> dict[str, str]:
    """Every long-form screen, by callback name, for length checks and tests."""

    return {
        "privacy": privacy_policy(),
        "terms": terms_of_use(),
        "tariffs": tariffs_text(),
    }


def check_document_lengths() -> None:
    """Raise if any screen would be rejected by the Bot API."""

    too_long = {
        name: len(body)
        for name, body in documents().items()
        if len(body) > TELEGRAM_MESSAGE_LIMIT
    }
    if too_long:
        details = ", ".join(f"{name}={size}" for name, size in sorted(too_long.items()))
        raise RuntimeError(
            f"Mirror documents exceed the {TELEGRAM_MESSAGE_LIMIT}-character limit: {details}"
        )
