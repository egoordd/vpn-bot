from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main_menu import help_keyboard
from bot.navigation import show_screen
from bot.texts import bq
from config import settings

router = Router()


def _help_text(telegram_id: int) -> str:
    return (
        "❓ <b>Помощь</b>\n\n"
        "📱 <b>Как подключиться:</b>\n"
        + bq(
            "1️⃣ Купите подписку и откройте «📋 Мои подписки»",
            "2️⃣ «Подключить устройство» → импортируйте ссылку",
            "3️⃣ Включите туннель в приложении — готово",
        )
        + "\n\n📲 <b>Приложения:</b>\n"
        + bq(
            "🍏 iOS — Happ / V2RayTun (App Store)",
            "🤖 Android — Happ / Hiddify (Google Play)",
            "💻 Windows / macOS — Hiddify",
        )
        + "\n\n🌍 В подписке несколько локаций — переключайтесь между странами "
        "прямо в приложении (выбор сервера).\n\n"
        "💬 <b>Поддержка:</b>\n"
        + bq(
            f"Контакт: {settings.support_contact}",
            f"Ваш ID: <code>{telegram_id}</code>",
        )
        + "\n\nНапишите в поддержку, приложите ID и опишите проблему."
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(_help_text(message.from_user.id), reply_markup=help_keyboard(settings.support_contact))


@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery) -> None:
    await show_screen(callback, _help_text(callback.from_user.id), help_keyboard(settings.support_contact))
    await callback.answer()
