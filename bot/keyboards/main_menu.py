from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить VPN", callback_data="buy_vpn")],
            [InlineKeyboardButton(text="Моя подписка", callback_data="my_subscription")],
            [InlineKeyboardButton(text="Получить ключ", callback_data="get_key")],
            [
                InlineKeyboardButton(text="Инструкция", callback_data="instructions"),
                InlineKeyboardButton(text="Поддержка", callback_data="support"),
            ],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад в меню", callback_data="main_menu")],
        ]
    )
