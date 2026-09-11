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


def test_subscriber_menu_is_short_and_sells_nothing_by_itself() -> None:
    markup = mirror_bot.main_menu_keyboard(has_subscription=True, trial_available=False)
    callbacks = _callback_values(markup)

    assert callbacks == ["connect_device", "tariffs", "promo_enter", "about", "help"]
    assert len(markup["inline_keyboard"]) == 3


def test_newcomer_gets_the_free_trial_first() -> None:
    markup = mirror_bot.main_menu_keyboard(has_subscription=False, trial_available=True)

    assert _callback_values(markup) == ["activate_trial", "tariffs", "about", "help"]


def test_lapsed_user_is_sent_to_the_tariffs() -> None:
    markup = mirror_bot.main_menu_keyboard(has_subscription=False, trial_available=False)

    assert _callback_values(markup) == ["tariffs", "promo_enter", "about", "help"]


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


def _subscription(**overrides):
    from datetime import datetime, timezone

    values = dict(
        id=7,
        plan="standard_1m",
        expires_at=datetime(2026, 10, 11, 3, 30, tzinfo=timezone.utc),
        traffic_used_bytes=12 * 1024**3,
        traffic_limit_bytes=150 * 1024**3,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _mirror_surfaces() -> dict[str, str]:
    """Every text the mirror shows to a user or a reviewer."""

    from services import mirror_legal

    surfaces = dict(mirror_legal.documents())
    surfaces["help"] = mirror_bot._help_text(1)
    surfaces["about"] = mirror_bot._about_text()
    surfaces["welcome"] = mirror_bot._menu_text([], trial_available=True)
    surfaces["subscriber"] = mirror_bot._menu_text([_subscription()], trial_available=False)
    surfaces["lapsed"] = mirror_bot._menu_text([], trial_available=False)
    surfaces["connect"] = mirror_bot.connection_screen(_subscription(), "https://unlockru.site/sub/T")[0]
    surfaces["description"] = mirror_legal.bot_description()
    surfaces["short_description"] = mirror_legal.bot_short_description()
    return surfaces


def test_documents_and_support_are_one_tap_from_the_menu() -> None:
    """The bank wants documents, prices and support reachable from the interface."""

    menu = _callback_values(
        mirror_bot.main_menu_keyboard(has_subscription=False, trial_available=False)
    )
    about_markup = mirror_bot._about_keyboard()
    urls = [
        button["url"]
        for row in about_markup["inline_keyboard"]
        for button in row
        if "url" in button
    ]

    assert {"tariffs", "about", "help"} <= set(menu)
    assert {"terms", "privacy"} <= set(_callback_values(about_markup))
    assert any("t.me/" in url for url in urls), "нет прямой кнопки поддержки"


def test_about_claims_only_what_the_service_really_offers() -> None:
    text = mirror_bot._about_text()
    lowered = text.lower()

    assert "от 100 ₽" in text
    assert "200 ГБ" in text
    assert "3 устройств" in text
    for claim in ("безлимит", "24/7", "тысяч", "лучшие цены"):
        assert claim not in lowered, claim


def test_about_links_to_neither_the_channel_nor_the_site() -> None:
    markup = mirror_bot._about_keyboard()
    urls = [b["url"] for row in markup["inline_keyboard"] for b in row if "url" in b]

    assert all("UnlockAccess" not in url and "unlockproject" not in url for url in urls)
    assert "unlockproject" not in mirror_bot._about_text()


def test_welcome_names_the_service_and_the_free_trial() -> None:
    from bot.texts import trial_days

    text = mirror_bot._menu_text([], trial_available=True)

    assert "Добро пожаловать" in text
    assert trial_days() in text


def test_subscriber_sees_the_subscription_not_a_profile() -> None:
    text = mirror_bot._menu_text([_subscription()], trial_available=False)

    assert "Standard 1 месяц" in text
    assert "11 октября 2026" in text
    assert "12 из 150 ГБ" in text
    assert "Профиль" not in text


def test_no_screen_still_says_payment_is_unavailable(monkeypatch) -> None:
    from services import mirror_platega

    monkeypatch.setattr(mirror_platega, "MERCHANT_ID", "m")
    monkeypatch.setattr(mirror_platega, "SECRET", "s")

    for text in (
        mirror_bot._menu_text([], trial_available=False),
        mirror_bot._subscriptions_text([]),
    ):
        assert "недоступна" not in text


def test_connecting_never_sends_anyone_to_the_website(monkeypatch) -> None:
    """This bot knows nothing of the site: the import page is the subscription host's own."""

    monkeypatch.setattr(mirror_bot.settings, "WEB_BASE_URL", "https://unlockproject.site")

    text, markup = mirror_bot.connection_screen(_subscription(), "https://unlockru.site/sub/TOKEN")
    urls = [button["url"] for row in markup["inline_keyboard"] for button in row if "url" in button]

    assert urls == ["https://unlockru.site/happ/TOKEN"]
    assert "unlockproject" not in text
    assert "https://unlockru.site/sub/TOKEN" in text


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


def test_the_review_code_is_gone_once_the_desk_is_approved() -> None:
    from services import mirror_legal

    assert mirror_legal.VERIFICATION_CODE == ""
    assert "PLAT" not in mirror_bot._help_text(1)
    assert mirror_legal.bot_display_name() == mirror_legal.PROJECT_NAME


def test_a_review_code_still_shows_wherever_it_must(monkeypatch) -> None:
    from services import mirror_legal

    monkeypatch.setattr(mirror_legal, "VERIFICATION_CODE", "PLAT")

    assert "PLAT" in mirror_bot._help_text(1)
    assert mirror_legal.bot_display_name() == "UnLock VPN PLAT"


def test_tariffs_screen_lists_real_prices() -> None:
    from services import mirror_legal
    from services.tariffs import TARIFFS

    body = mirror_legal.tariffs_text()
    for tariff in TARIFFS.values():
        if tariff.price_rub > 0:
            assert f"{tariff.price_rub} ₽" in body, f"нет цены тарифа {tariff.code}"


def test_tariffs_show_the_monthly_price_of_longer_plans() -> None:
    from services import mirror_legal

    body = mirror_legal.tariffs_text()

    assert "3 месяца" in body and "133 ₽/мес" in body
    assert "12 месяцев" in body and "100 ₽/мес" in body


def test_bot_profile_texts_fit_telegram_limits() -> None:
    from services import mirror_legal

    assert len(mirror_legal.bot_description()) <= 512
    assert len(mirror_legal.bot_short_description()) <= 120
