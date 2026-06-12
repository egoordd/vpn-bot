import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.texts import bq
from database.models import Node, Subscription
from database.repository import Repository
from services.autoscaler import AutoscalerError, ProvisionNodeRequest, move_subscription_to_region
from services.tariffs import PREMIUM_REGIONS, resolve_premium_region

logger = logging.getLogger(__name__)
router = Router()


def _region_title(region_code: str | None) -> str:
    if not region_code:
        return "ещё не назначена"
    try:
        return resolve_premium_region(region_code).title
    except ValueError:
        return region_code


async def _node_by_ref(repo: Repository, node_ref: str) -> Node | None:
    if node_ref.startswith("db:"):
        try:
            return await repo.get_node(int(node_ref.removeprefix("db:")))
        except ValueError:
            return None
    node = await repo.get_node_by_panel_node_id(node_ref)
    if node is not None:
        return node
    try:
        return await repo.get_node(int(node_ref))
    except ValueError:
        return None


async def _subscription_region(repo: Repository, subscription: Subscription) -> str | None:
    for node_ref in subscription.node_ids or []:
        node = await _node_by_ref(repo, str(node_ref))
        if node is not None:
            return node.region
    return None


def _locations_keyboard(current_region: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅ ' if code == current_region else '🌍 '}{region.title}",
                callback_data=f"set_location:{code}",
            )
        ]
        for code, region in PREMIUM_REGIONS.items()
    ]
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_text(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    if not callback.message:
        return
    if getattr(callback.message, "photo", None):
        await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup)


@router.callback_query(F.data == "locations")
async def locations_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        subscription = await repo.get_active_subscription(user.id)
        if subscription is not None and subscription.tier == "premium":
            current_region = await _subscription_region(repo, subscription)
        else:
            current_region = None

    if subscription is None:
        text = (
            "🌍 <b>Локации</b>\n\n"
            + bq("🔒 Доступно на Premium-тарифе")
            + "\n\nКупи Premium — и выбирай регион подключения."
        )
        keyboard = back_to_menu_keyboard()
    elif subscription.tier != "premium":
        text = (
            "🌍 <b>Локации</b>\n\n"
            + bq(
                "🔒 Выбор локации доступен на Premium",
                "🌐 Сейчас: общие локации из ссылки-подписки",
            )
        )
        keyboard = back_to_menu_keyboard()
    else:
        text = (
            "🌍 <b>Premium-локации</b>\n\n"
            + bq(f"📍 Текущая локация: {_region_title(current_region)}")
            + "\n\nВыбери другой регион. Если свободной ноды там нет, "
            "сервер подготовится автоматически (~2 минуты)."
        )
        keyboard = _locations_keyboard(current_region)

    await _edit_text(callback, text, keyboard)
    await callback.answer()


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
        subscription = await repo.get_active_subscription(user.id)
        if subscription is None or subscription.tier != "premium":
            await callback.answer("Смена локации доступна на Premium", show_alert=True)
            return

        current_region = await _subscription_region(repo, subscription)
        if current_region == region.code:
            await callback.answer("Эта локация уже выбрана")
            return

        await _edit_text(
            callback,
            "⏳ <b>Готовлю локацию</b>\n\n"
            + bq(f"📍 Регион: {region.title}")
            + "\n\nОбычно это занимает около 2 минут.",
            back_to_menu_keyboard(),
        )
        await callback.answer("Готовлю локацию")

        try:
            node = await move_subscription_to_region(
                session=session,
                subscription_id=subscription.id,
                region=region.code,
                provision_request=ProvisionNodeRequest(region=region.code, country_code=region.country_code),
            )
        except AutoscalerError:
            logger.exception("Failed to move premium subscription_id=%s to region=%s", subscription.id, region.code)
            await _edit_text(
                callback,
                "Не удалось сменить локацию. Попробуйте позже или напишите в поддержку.",
                back_to_menu_keyboard(),
            )
            return
        except Exception:
            logger.exception("Unexpected premium location switch failure subscription_id=%s", subscription.id)
            await _edit_text(
                callback,
                "Не удалось сменить локацию. Попробуйте позже или напишите в поддержку.",
                back_to_menu_keyboard(),
            )
            return

    text = (
        "✅ <b>Локация обновлена</b>\n\n"
        + bq(f"📍 Текущая локация: {_region_title(node.region)}")
        + "\n\nСсылка-подписка осталась прежней; клиент подтянет обновление автоматически."
    )
    await _edit_text(callback, text, _locations_keyboard(node.region))
