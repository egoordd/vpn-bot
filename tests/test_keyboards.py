import pytest

from bot.keyboards.main_menu import (
    active_subscription_keyboard,
    back_to_menu_keyboard,
    landing_keyboard,
    main_menu_keyboard,
    premium_location_keyboard,
)


@pytest.mark.unit
def test_keyboards_have_expected_primary_actions():
    assert landing_keyboard().inline_keyboard[0][0].callback_data == "buy:standard_1m"
    assert landing_keyboard().inline_keyboard[3][0].callback_data == "buy:standard_12m"
    assert landing_keyboard().inline_keyboard[4][0].callback_data == "buy:premium_1m"
    assert landing_keyboard().inline_keyboard[7][0].callback_data == "buy:premium_12m"
    assert active_subscription_keyboard().inline_keyboard[0][0].callback_data == "connect_device"
    assert active_subscription_keyboard().inline_keyboard[1][0].callback_data == "locations"
    assert back_to_menu_keyboard().inline_keyboard[0][0].callback_data == "main_menu"
    assert main_menu_keyboard().inline_keyboard[0][0].callback_data == "buy:standard_1m"
    assert premium_location_keyboard("premium_1m").inline_keyboard[0][0].callback_data == "buy_region:premium_1m:ams"
