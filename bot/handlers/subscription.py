import html

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq, format_gb, format_msk
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
        text = (
            "🔑 <b>Моя подписка</b>\n\n"
            + bq("⚡️ Статус: ❌ не активна")
            + "\n\nВыберите тариф в меню — ссылка-подписка придёт автоматически."
        )
    else:
        status = "✅ активна" if info["is_active"] else "❌ неактивна"
        card_lines = [
            f"💎 Тариф: {html.escape(str(info.get('plan_title') or info.get('plan') or '—'))}",
            f"⚡️ Статус: {status}",
        ]
        if info.get("traffic_limit_bytes") is not None:
            used = format_gb(info.get("traffic_used_bytes") or 0)
            limit = format_gb(info.get("traffic_limit_bytes"))
            card_lines.append(f"📊 Трафик: {used} / {limit} ГБ")
        if info.get("device_limit") is not None:
            card_lines.append(f"📱 Устройств: до {info['device_limit']}")

        sections = ["🔑 <b>Моя подписка</b>\n\n" + bq(*card_lines)]
        if info.get("subscription_url"):
            sections.append(
                "🔗 <b>Ссылка-подписка:</b>\n"
                f"<code>{html.escape(str(info['subscription_url']))}</code>"
            )
        if info.get("expires_at"):
            sections.append(f"📅 <b>Действует до:</b> {format_msk(info['expires_at'])}")
        text = "\n\n".join(sections)

    await show_screen(callback, text, back_to_menu_keyboard())
    await callback.answer()
