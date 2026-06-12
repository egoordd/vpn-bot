import pytest

from bot.keyboards.main_menu import (
    active_subscription_keyboard,
    back_to_menu_keyboard,
    landing_keyboard,
    main_menu_keyboard,
    premium_location_keyboard,
    tier_plans_keyboard,
    tier_select_keyboard,
)


@pytest.mark.unit
def test_landing_keyboard_offers_tier_choice():
    keyboard = landing_keyboard().inline_keyboard
    assert keyboard[0][0].callback_data == "buy_tier:standard"
    assert keyboard[1][0].callback_data == "buy_tier:premium"
    assert keyboard[2][0].callback_data == "wallet"
    assert keyboard[2][1].callback_data == "referral"
    assert keyboard[3][0].callback_data == "support"
    assert main_menu_keyboard().inline_keyboard[0][0].callback_data == "buy_tier:standard"


@pytest.mark.unit
def test_tier_buttons_show_min_monthly_price():
    keyboard = landing_keyboard().inline_keyboard
    # standard_12m: 1199 / 12 mo = 99, premium_12m: 2999 / 12 mo = 249
    assert "99\u20bd/\u043c\u0435\u0441" in keyboard[0][0].text
    assert "249\u20bd/\u043c\u0435\u0441" in keyboard[1][0].text


@pytest.mark.unit
def test_tier_select_keyboard_has_back_to_main_menu():
    keyboard = tier_select_keyboard().inline_keyboard
    assert keyboard[0][0].callback_data == "buy_tier:standard"
    assert keyboard[-1][0].callback_data == "main_menu"


@pytest.mark.unit
def test_tier_plans_keyboard_lists_only_tier_plans():
    standard = tier_plans_keyboard("standard").inline_keyboard
    assert [row[0].callback_data for row in standard[:-1]] == [
        "buy:standard_1m",
        "buy:standard_3m",
        "buy:standard_6m",
        "buy:standard_12m",
    ]
    assert standard[-1][0].callback_data == "buy_menu"

    premium = tier_plans_keyboard("premium").inline_keyboard
    assert [row[0].callback_data for row in premium[:-1]] == [
        "buy:premium_1m",
        "buy:premium_3m",
        "buy:premium_6m",
        "buy:premium_12m",
    ]
    assert "\u20bd" in premium[0][0].text


@pytest.mark.unit
def test_other_keyboards_keep_primary_actions():
    assert active_subscription_keyboard().inline_keyboard[0][0].callback_data == "connect_device"
    assert active_subscription_keyboard().inline_keyboard[1][0].callback_data == "locations"
    assert back_to_menu_keyboard().inline_keyboard[0][0].callback_data == "main_menu"
    assert premium_location_keyboard("premium_1m").inline_keyboard[0][0].callback_data == "buy_region:premium_1m:ams"
