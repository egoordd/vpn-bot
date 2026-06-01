import pytest

from bot.keyboards.main_menu import active_subscription_keyboard, back_to_menu_keyboard, landing_keyboard, main_menu_keyboard


@pytest.mark.unit
def test_keyboards_have_expected_primary_actions():
    assert landing_keyboard().inline_keyboard[0][0].callback_data == "buy:1m"
    assert active_subscription_keyboard().inline_keyboard[0][0].callback_data == "get_key"
    assert back_to_menu_keyboard().inline_keyboard[0][0].callback_data == "main_menu"
    assert main_menu_keyboard().inline_keyboard[0][0].callback_data == "buy:1m"
