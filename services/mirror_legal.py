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


# Shown to the acquirer's reviewer while the payment desk is being approved.
# Remove once Platega confirms registration.
VERIFICATION_CODE = "PLAT"

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
        "Действующая редакция всегда доступна в этом боте по кнопке "
        "«🔒 Политика конфиденциальности».\n\n"
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
        "Действующие тарифы приведены в боте по кнопке «💳 Тарифы». Оплата вносится "
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
        "доступна по кнопке «📄 Пользовательское соглашение». Продолжение использования "
        "Сервиса означает согласие с изменениями.\n\n"
        "<b>11. Контакты</b>\n"
        f"Поддержка: {_support()}"
    )


def _tariff_line(tariff: Tariff) -> str:
    devices = tariff.device_limit if tariff.device_limit is not None else "∞"
    traffic = f"{tariff.traffic_gb} ГБ" if tariff.traffic_gb is not None else "без учёта"
    period = "в месяц" if tariff.traffic_resets_monthly else "на весь срок"
    price = "бесплатно" if tariff.price_rub == 0 else f"{tariff.price_rub} ₽"
    return (
        f"<b>{tariff.title}</b> — {price}\n"
        f"Срок: {tariff.duration_days} дн. · Трафик: {traffic} {period} · "
        f"Устройств: до {devices}"
    )


def tariffs_text() -> str:
    ordered = sorted(TARIFFS.values(), key=lambda item: item.sort_order)
    trial = [item for item in ordered if item.price_rub == 0]
    paid = [item for item in ordered if item.price_rub > 0]

    sections = ["💳 <b>Тарифы</b>"]
    if trial:
        sections.append(
            "<b>Пробный доступ</b>\n<blockquote>"
            + "\n\n".join(_tariff_line(item) for item in trial)
            + "\nПредоставляется один раз новому пользователю.</blockquote>"
        )
    if paid:
        sections.append(
            "<b>Платные тарифы</b>\n<blockquote>"
            + "\n\n".join(_tariff_line(item) for item in paid)
            + "</blockquote>"
        )
    sections.append(
        "Оплата вносится авансом за выбранный период. Подписка включается "
        "автоматически после подтверждения платежа.\n"
        "Условия возврата — в разделе «📄 Пользовательское соглашение»."
    )
    return "\n\n".join(sections)


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
