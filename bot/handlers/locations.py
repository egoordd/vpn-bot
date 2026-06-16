import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.navigation import show_screen
from bot.texts import bq
from config import settings
from database.models import Subscription
from database.repository import Repository
from services.subscription import StaticRegionError, switch_premium_region
from services.tariffs import PREMIUM_REGIONS, resolve_premium_region

logger = logging.getLogger(__name__)
router = Router()


def _region_title(region_code: str | None) -> str:
    if not region_code:
        return "ещё не выбрана"
    try:
        region = resolve_premium_region(region_code)
        return f"{region.flag} {region.title}"
    except ValueError:
        return region_code


def _is_static(region_code: str) -> bool:
    return settings.marzban_inbounds_for_region(region_code) is not None


def _premium_active(subscriptions: list[Subscription]) -> Subscription | None:
    return next((s for s in subscriptions if s.tier == "premium"), None)


def _locations_keyboard(current_region: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for code, region in PREMIUM_REGIONS.items():
        if _is_static(code):
            mark = "✅ " if code == current_region else f"{region.flag} "
            rows.append([InlineKeyboardButton(text=f"{mark}{region.title}", callback_data=f"set_location:{code}")])
        else:
            rows.append([InlineKeyboardButton(text=f"🔜 {region.flag} {region.title} (скоро)", callback_data="location_soon")])
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_text(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    await show_screen(callback, text, reply_markup)


# Shared locations available in the standard (multi-location) subscription.
# Switched on the client side (the subscription lists all of them).
SHARED_LOCATIONS = ["🇺🇸 США", "🇳🇱 Нидерланды"]


@router.callback_query(F.data == "locations")
async def locations_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    text = (
        "🌍 <b>Локации</b>\n\n"
        "В вашей подписке доступны страны:\n"
        + bq(*SHARED_LOCATIONS)
        + "\n\n🔀 Переключайтесь между ними <b>прямо в приложении</b> "
        "(выбор сервера в Happ / V2RayTun / Hiddify) — ссылка-подписка одна.\n\n"
        "💎 Premium с фиксированным IP и низкой плотностью — скоро."
    )
    await _edit_text(callback, text, back_to_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "location_soon")
async def location_soon_handler(callback: CallbackQuery) -> None:
    await callback.answer("Эта локация скоро будет доступна.", show_alert=True)


@router.callback_query(F.data.startswith("set_location:"))
async def set_location_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    raw_region = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    try:
        region = resolve_premium_region(raw_region)
    except ValueError:
        await callback.answer("Локация не найдена", show_alert=True)
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        premium = _premium_active(await repo.list_active_subscriptions(user.id))
        if premium is None:
            await callback.answer("Смена локации доступна на Premium", show_alert=True)
            return
        if premium.region == region.code:
            await callback.answer("Эта локация уже выбрана")
            return

        try:
            updated = await switch_premium_region(session, user.id, region.code)
        except StaticRegionError:
            await callback.answer("Эта локация скоро будет доступна.", show_alert=True)
            return
        except Exception:
            logger.exception("Failed to switch premium subscription_id=%s to region=%s", premium.id, region.code)
            await _edit_text(
                callback,
                "Не удалось сменить локацию. Попробуйте позже или напишите в поддержку.",
                back_to_menu_keyboard(),
            )
            return

    text = (
        "✅ <b>Локация обновлена</b>\n\n"
        + bq(f"📍 Текущая локация: {_region_title(updated.region)}")
        + "\n\nОбновите подписку в приложении (или переподключитесь) — трафик пойдёт через новый регион."
    )
    await _edit_text(callback, text, _locations_keyboard(updated.region))
    await callback.answer("Локация обновлена")
