from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import back_to_menu_keyboard
from config import settings

router = Router()


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery) -> None:
    text = (
        "Поддержка\n\n"
        f"Напишите нам: {settings.support_contact}\n"
        "Укажите ваш Telegram ID и кратко опишите проблему."
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
