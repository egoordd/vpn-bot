from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.navigation import show_screen
from bot.texts import bq
from config import settings

router = Router()


def _support_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if settings.SUPPORT_BOT_USERNAME:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✍️ Написать в поддержку",
                    url=f"https://t.me/{settings.SUPPORT_BOT_USERNAME}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery) -> None:
    text = (
        "🆘 <b>Поддержка</b>\n\n"
        + bq(f"🆔 Ваш ID: <code>{callback.from_user.id}</code>")
        + "\n\nНажмите «Написать в поддержку» — откроется бот поддержки, "
        "там опишите проблему. Мы ответим в том же чате."
    )
    await show_screen(callback, text, _support_keyboard())
    await callback.answer()
