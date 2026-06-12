from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.texts import bq
from config import settings

router = Router()


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery) -> None:
    text = (
        "🆘 <b>Поддержка</b>\n\n"
        + bq(
            f"💬 Контакт: {settings.support_contact}",
            f"🆔 Твой ID: <code>{callback.from_user.id}</code>",
        )
        + "\n\nНапиши нам, приложи свой ID и кратко опиши проблему — так мы поможем быстрее."
    )
    if callback.message:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=back_to_menu_keyboard())
        else:
            await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
