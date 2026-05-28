from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import active_subscription_keyboard, landing_keyboard
from database.repository import Repository

router = Router()

BANNER_PATH = "assets/banner.png"

LANDING_TEXT = (
    "<b>UnLock</b>\n"
    "Быстрый VPN за копейки\n\n"
    "Выбери тариф, оплати через CryptoBot и получи WireGuard-ключ автоматически."
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _active_text(expires_at: datetime) -> str:
    return (
        "<b>UnLock</b>\n"
        f"✅ Подписка активна до {_aware(expires_at):%d.%m.%Y %H:%M} UTC\n\n"
        "Можно получить WireGuard-ключ или продлить доступ."
    )


async def _menu_state(
    session_pool: async_sessionmaker[AsyncSession],
    telegram_id: int,
    username: str | None,
) -> tuple[str, InlineKeyboardMarkup]:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=telegram_id, username=username)
        subscription = await repo.get_active_subscription(user.id)

    if subscription is None:
        return LANDING_TEXT, landing_keyboard()
    return _active_text(subscription.expires_at), active_subscription_keyboard()


@router.message(CommandStart())
async def start_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    text, keyboard = await _menu_state(
        session_pool=session_pool,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    await message.answer_photo(FSInputFile(BANNER_PATH), caption=text, reply_markup=keyboard)
