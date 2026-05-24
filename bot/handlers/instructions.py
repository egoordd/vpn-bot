from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import back_to_menu_keyboard

router = Router()


INSTRUCTIONS_TEXT = (
    "<b>Как подключиться через WireGuard</b>\n\n"
    "<b>iOS / Android</b>\n"
    "1. Установите WireGuard из App Store или Google Play.\n"
    "2. Нажмите «+» и выберите импорт из QR-кода или файла.\n"
    "3. Включите созданный туннель.\n\n"
    "<b>Windows</b>\n"
    "1. Установите WireGuard с официального сайта wireguard.com/install.\n"
    "2. Нажмите Import tunnel(s) from file.\n"
    "3. Выберите .conf файл и активируйте туннель.\n\n"
    "<b>macOS</b>\n"
    "1. Установите WireGuard из App Store.\n"
    "2. Импортируйте .conf файл или отсканируйте QR-код.\n"
    "3. Включите туннель.\n\n"
    "Если подключение не работает, проверьте дату окончания подписки и напишите в поддержку."
)


@router.callback_query(F.data == "instructions")
async def instructions_handler(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text(INSTRUCTIONS_TEXT, reply_markup=back_to_menu_keyboard())
    await callback.answer()
