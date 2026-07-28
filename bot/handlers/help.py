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
        "<b>Как подключиться</b>\n"
        + bq(
            "1️⃣ Купите подписку и откройте «Мои подписки»",
            "2️⃣ «Подключить устройство» → импортируйте ссылку",
            "3️⃣ Включите туннель в приложении — готово",
        )
        # Пункт про выбор локаций убран: «Авто-обход» выбирает сервер сам, а
        # список стран пользователь и так видит в приложении.
        + "\n\n<b>Приложения</b>\n"
        + bq(
            "iOS — Happ / V2RayTun",
            "Android — Happ / Hiddify",
            "Windows / macOS — Hiddify",
        )
        # Контакт и ID — это и есть инструкция «напишите, приложив ID»,
        # отдельная строка про то же только повторяла блок под ним.
        + "\n\n<b>Поддержка</b> — напишите и приложите ID\n"
        + bq(
            f"{settings.support_contact}",
            f"Ваш ID: <code>{telegram_id}</code>",
        )
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(_help_text(message.from_user.id), reply_markup=help_keyboard(settings.support_contact))


@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery) -> None:
    await show_screen(callback, _help_text(callback.from_user.id), help_keyboard(settings.support_contact))
    await callback.answer()
