from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq
from config import settings

router = Router()


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery) -> None:
    text = (
        "🆘 <b>Поддержка</b>\n\n"
        + bq(
            f"💬 Контакт: {settings.support_contact}",
            f"🆔 Ваш ID: <code>{callback.from_user.id}</code>",
        )
        + "\n\nНапишите в поддержку, приложите свой ID и кратко опишите проблему."
    )
    await show_screen(callback, text, back_to_menu_keyboard())
    await callback.answer()
