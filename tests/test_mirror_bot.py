from types import SimpleNamespace

import pytest

from services import mirror_bot


def _callback_values(markup: dict) -> list[str]:
    return [
        button["callback_data"]
        for row in markup["inline_keyboard"]
        for button in row
        if "callback_data" in button
    ]


def test_mirror_menu_has_no_payment_or_renewal_actions() -> None:
    markup = mirror_bot.main_menu_keyboard(
        has_subscription=True,
        trial_available=True,
    )
    callbacks = _callback_values(markup)

    assert "my_subs" in callbacks
    assert "activate_trial" in callbacks
    assert "promo_enter" in callbacks
    assert "buy_menu" not in callbacks
    assert "renew_menu" not in callbacks


@pytest.mark.parametrize(
    "value",
    [
        "buy_menu",
        "renew_menu",
        "buy:standard_1m",
        "buy_tier:standard",
        "renew_sub:15",
        "payyk:standard_1m",
        "ykemail:standard_1m",
    ],
)
def test_payment_callbacks_are_blocked(value: str) -> None:
    assert mirror_bot.is_payment_callback(value)


def test_non_payment_callbacks_are_not_blocked() -> None:
    assert not mirror_bot.is_payment_callback("connect_device")
    assert not mirror_bot.is_payment_callback("activate_trial")
    assert not mirror_bot.is_payment_callback("promo_enter")


def test_payment_guard_reports_configured_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        YOOKASSA_SHOP_ID="shop",
        yookassa_secret_key="",
        TRIBUTE_API_KEY="",
        TRIBUTE_DEFAULT_PLAN="",
        TRIBUTE_PLAN_MAP="{}",
        TRIBUTE_PAY_LINKS="{}",
    )
    monkeypatch.setattr(mirror_bot, "settings", fake)

    assert mirror_bot.configured_payment_fields() == ["YOOKASSA_SHOP_ID"]
    with pytest.raises(RuntimeError, match="YOOKASSA_SHOP_ID"):
        mirror_bot.assert_payments_disabled()


def test_payment_guard_accepts_empty_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = SimpleNamespace(
        YOOKASSA_SHOP_ID="",
        yookassa_secret_key="",
        TRIBUTE_API_KEY="",
        TRIBUTE_DEFAULT_PLAN="",
        TRIBUTE_PLAN_MAP="{}",
        TRIBUTE_PAY_LINKS="{}",
    )
    monkeypatch.setattr(mirror_bot, "settings", fake)

    mirror_bot.assert_payments_disabled()


# --- Требования эквайера к зеркалу -------------------------------------------
# Банк проверяет бота перед регистрацией кассы: документы, контакт поддержки и
# цены должны быть доступны из интерфейса, а формулировки — нейтральными.

RESTRICTED_VOCABULARY = (
    "обход",
    "блокиров",
    "цензур",
    "dpi",
    "тспу",
    "глушилк",
    "белый список",
    "белых список",
    "чебурнет",
    "ускорител",
    "ограничени",
    "замедлен",
    "разблокир",
)

PERSONAL_DATA_MARKERS = ("инн", "дегтяр", "самозанят", "220454839571")


def _mirror_surfaces() -> dict[str, str]:
    """Every long-form text the mirror shows to a user or a reviewer."""

    from services import mirror_legal

    surfaces = dict(mirror_legal.documents())
    surfaces["help"] = mirror_bot._help_text(1)
    return surfaces


def test_menu_exposes_documents_tariffs_and_support() -> None:
    markup = mirror_bot.main_menu_keyboard(
        has_subscription=False,
        trial_available=False,
    )
    callbacks = _callback_values(markup)
    urls = [
        button["url"]
        for row in markup["inline_keyboard"]
        for button in row
        if "url" in button
    ]

    assert "tariffs" in callbacks
    assert "terms" in callbacks
    assert "privacy" in callbacks
    assert any("t.me/" in url for url in urls), "нет прямой кнопки поддержки"


def test_documents_fit_the_telegram_message_limit() -> None:
    from services import mirror_legal

    mirror_legal.check_document_lengths()


@pytest.mark.parametrize("name", ["tariffs", "terms", "privacy"])
def test_every_document_is_reachable(name: str) -> None:
    assert name in mirror_bot.DOCUMENT_CALLBACKS
    assert mirror_bot._document_text(name).strip()


def test_mirror_texts_avoid_restricted_vocabulary() -> None:
    offenders = {
        f"{surface}:{word}"
        for surface, body in _mirror_surfaces().items()
        for word in RESTRICTED_VOCABULARY
        if word in body.lower()
    }
    assert not offenders, f"запрещённая лексика в текстах зеркала: {sorted(offenders)}"


def test_mirror_texts_carry_no_personal_data() -> None:
    offenders = {
        f"{surface}:{marker}"
        for surface, body in _mirror_surfaces().items()
        for marker in PERSONAL_DATA_MARKERS
        if marker in body.lower()
    }
    assert not offenders, f"персональные данные в текстах зеркала: {sorted(offenders)}"


def test_help_carries_the_verification_code() -> None:
    from services import mirror_legal

    assert mirror_legal.VERIFICATION_CODE in mirror_bot._help_text(1)


def test_tariffs_screen_lists_real_prices() -> None:
    from services import mirror_legal
    from services.tariffs import TARIFFS

    body = mirror_legal.tariffs_text()
    for tariff in TARIFFS.values():
        if tariff.price_rub > 0:
            assert f"{tariff.price_rub} ₽" in body, f"нет цены тарифа {tariff.code}"


def test_bot_name_carries_the_verification_code() -> None:
    from services import mirror_legal

    name = mirror_legal.bot_display_name()
    assert mirror_legal.PROJECT_NAME in name
    assert mirror_legal.VERIFICATION_CODE in name
    assert len(name) <= mirror_legal.TELEGRAM_NAME_LIMIT
