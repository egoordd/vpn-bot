import pytest

from bot.keyboards.main_menu import (
    back_to_menu_keyboard,
    main_menu_keyboard,
    my_subs_keyboard,
    tier_plans_keyboard,
)


@pytest.mark.unit
def test_main_menu_buy_first_then_subs_when_active():
    no_sub = main_menu_keyboard(has_subscription=False).inline_keyboard
    assert no_sub[0][0].callback_data == "buy_menu"
    callbacks = [b.callback_data for row in no_sub for b in row]
    assert "my_subs" not in callbacks  # no subs -> no "Мои подписки"
    assert "profile" not in callbacks  # profile shown on the menu itself, no button
    assert "help" in callbacks

    active = main_menu_keyboard(has_subscription=True).inline_keyboard
    assert active[0][0].callback_data == "buy_menu"
    active_cbs = [b.callback_data for row in active for b in row]
    assert "my_subs" in active_cbs and "renew_menu" in active_cbs


@pytest.mark.unit
def test_main_menu_has_no_clutter_buttons():
    # wallet / invite / support moved to commands, not the main grid
    cbs = [b.callback_data for row in main_menu_keyboard(True).inline_keyboard for b in row]
    assert "wallet" not in cbs and "referral" not in cbs and "support" not in cbs


@pytest.mark.unit
def test_tier_plans_keyboard_lists_only_tier_plans():
    standard = tier_plans_keyboard("standard").inline_keyboard
    assert [row[0].callback_data for row in standard[:-1]] == [
        "buy:standard_1m",
        "buy:standard_3m",
        "buy:standard_6m",
        "buy:standard_12m",
    ]
    assert standard[-1][0].callback_data == "main_menu"


@pytest.mark.unit
def test_tier_plans_keyboard_has_no_retired_plan_button():
    # Only current standard plans may be offered.
    standard = tier_plans_keyboard("standard").inline_keyboard
    callbacks = [b.callback_data for row in standard for b in row]
    assert not any("premium" in (cb or "") for cb in callbacks)


@pytest.mark.unit
def test_my_subs_keyboard_offers_connect():
    keyboard = my_subs_keyboard().inline_keyboard
    assert keyboard[0][0].callback_data == "connect_device"
    assert back_to_menu_keyboard().inline_keyboard[0][0].callback_data == "main_menu"


@pytest.mark.unit
def test_news_channel_button_is_offered_in_the_menu_and_on_the_help_screen():
    """The channel is the address of last resort when a domain gets blocked."""
    from bot.keyboards.main_menu import help_keyboard

    menu = main_menu_keyboard(has_subscription=True).inline_keyboard
    urls = [b.url for row in menu for b in row if b.url]
    assert any("t.me/UnlockAccess" in url for url in urls)

    help_rows = help_keyboard("@unlock_support_bot").inline_keyboard
    help_urls = [b.url for row in help_rows for b in row if b.url]
    assert any("t.me/UnlockAccess" in url for url in help_urls)


@pytest.mark.unit
def test_no_channel_configured_means_no_dead_button(monkeypatch):
    from bot.keyboards import main_menu as keyboards

    monkeypatch.setattr(type(keyboards.settings), "news_channel_url", property(lambda self: ""))
    menu = keyboards.main_menu_keyboard(has_subscription=True).inline_keyboard
    labels = [b.text for row in menu for b in row]
    assert not any("Новости" in label for label in labels)


@pytest.mark.unit
def test_the_platega_mirror_never_mentions_the_channel():
    """The acquirer's bank reviews the mirror; it knows nothing of a channel."""
    from pathlib import Path

    source = Path("services/mirror_bot.py").read_text(encoding="utf-8")
    assert "UnlockAccess" not in source
    assert "news_channel_url" not in source
