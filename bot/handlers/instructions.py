from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq

router = Router()


INSTRUCTIONS_TEXT = (
    "📖 <b>Как подключиться</b>\n\n"
    + bq(
        "1️⃣ Получи ссылку-подписку (выдаётся после /start или оплаты)",
        "2️⃣ Установи приложение для своей платформы",
        "3️⃣ Импортируй ссылку через «📱 Подключить устройство»",
        "4️⃣ Включи туннель и открой любой сайт",
    )
    + "\n\n📲 <b>Приложения:</b>\n"
    + bq(
        "🍏 iOS — Happ или V2RayTun (App Store)",
        "🤖 Android — Happ или Hiddify (Google Play)",
        "💻 Windows / macOS — Hiddify (hiddify.com)",
    )
    + "\n\nКонфиг обновляется сам — переустанавливать ничего не нужно.\n"
    "Не работает? Проверь срок подписки и напиши в поддержку."
)


@router.callback_query(F.data == "instructions")
async def instructions_handler(callback: CallbackQuery) -> None:
    await show_screen(callback, INSTRUCTIONS_TEXT, back_to_menu_keyboard())
    await callback.answer()
