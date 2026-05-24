from datetime import timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from database.repository import Repository
from services.subscription import get_subscription_info

router = Router()


@router.callback_query(F.data == "my_subscription")
async def subscription_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        info = await get_subscription_info(session=session, user_id=user.id)

    if not info["exists"]:
        text = "У вас пока нет подписки."
    else:
        expires_at = info["expires_at"]
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        status = "активна" if info["is_active"] else "неактивна"
        text = (
            f"Подписка: {status}\n"
            f"Тариф: {info['plan_title']}\n"
            f"Действует до: {expires_at:%d.%m.%Y %H:%M} UTC"
        )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
