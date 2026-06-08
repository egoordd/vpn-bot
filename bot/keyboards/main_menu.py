from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.payment import PLANS
from services.tariffs import PREMIUM_REGIONS


TARIFF_BUTTON_TITLES = {
    "standard_1m": "🚀 30 дней",
    "standard_3m": "💎 90 дней",
    "standard_6m": "👑 180 дней",
    "standard_12m": "🏆 12 месяцев",
    "premium_1m": "🌍 Premium 30 дней",
    "premium_3m": "🌍 Premium 90 дней",
    "premium_6m": "🌍 Premium 180 дней",
    "premium_12m": "🌍 Premium 12 месяцев",
}


def landing_keyboard() -> InlineKeyboardMarkup:
    tariff_rows = [
        [
            InlineKeyboardButton(
                text=f"{TARIFF_BUTTON_TITLES.get(code, str(plan['label']))} — {plan['rub_amount']}₽",
                callback_data=f"buy:{code}",
            )
        ]
        for code, plan in PLANS.items()
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *tariff_rows,
            [
                InlineKeyboardButton(text="❓ Поддержка", callback_data="support"),
                InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions"),
            ],
        ]
    )


def premium_location_keyboard(plan: str) -> InlineKeyboardMarkup:
    region_rows = [
        [
            InlineKeyboardButton(
                text=f"🌍 {region.title}",
                callback_data=f"buy_region:{plan}:{code}",
            )
        ]
        for code, region in PREMIUM_REGIONS.items()
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *region_rows,
            [InlineKeyboardButton(text="◀️ Назад", callback_data="buy_menu")],
        ]
    )


def active_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Подключить устройство", callback_data="connect_device")],
            [InlineKeyboardButton(text="🌍 Локации", callback_data="locations")],
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
