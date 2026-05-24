from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.payment import PLANS


def tariffs_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for plan_id, plan in PLANS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{plan['title']} - {plan['label']} - {plan['amount']} XTR",
                    callback_data=f"buy:{plan_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад в меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
