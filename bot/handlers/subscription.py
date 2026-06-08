from datetime import timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from database.repository import Repository
from services.subscription import get_subscription_info

router = Router()


def _format_gb(value: object) -> str:
    if value is None:
        return "без лимита"
    return f"{int(value) / 1024**3:.1f} ГБ"


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
        lines = [
            f"Подписка: {status}\n"
            f"Тариф: {info['plan_title']}\n"
            f"Действует до: {expires_at:%d.%m.%Y %H:%M} UTC"
        ]
        if info.get("tier"):
            lines.append(f"Тип: {info['tier']}")
        if info.get("traffic_limit_bytes") is not None:
            lines.append(
                "Трафик: "
                f"{_format_gb(info.get('traffic_used_bytes'))} / {_format_gb(info.get('traffic_limit_bytes'))}"
            )
        if info.get("device_limit") is not None:
            lines.append(f"Устройства: до {info['device_limit']}")
        if info.get("subscription_url"):
            lines.append(f"Ссылка-подписка:\n{info['subscription_url']}")
        text = "\n".join(lines)

    if callback.message:
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
