from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import main_menu_keyboard
from database.repository import Repository

router = Router()


WELCOME_TEXT = (
    "Добро пожаловать в VPN Bot.\n\n"
    "Здесь можно купить доступ, получить WireGuard-конфиг и проверить подписку."
)


@router.message(CommandStart())
async def start_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer()
