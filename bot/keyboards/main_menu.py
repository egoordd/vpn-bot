from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def landing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 30 дней — 149₽", callback_data="buy:1m")],
            [InlineKeyboardButton(text="💎 90 дней — 399₽", callback_data="buy:3m")],
            [InlineKeyboardButton(text="👑 180 дней — 699₽", callback_data="buy:6m")],
            [
                InlineKeyboardButton(text="❓ Поддержка", callback_data="support"),
                InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions"),
            ],
        ]
    )


def active_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Получить ключ", callback_data="get_key")],
            [InlineKeyboardButton(text="🔄 Продлить", callback_data="buy_menu")],
            [InlineKeyboardButton(text="❓ Поддержка", callback_data="support")],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return landing_keyboard()
