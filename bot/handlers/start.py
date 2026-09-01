import html
import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.banners import pick_start_banner, send_banner
from bot.keyboards.main_menu import main_menu_keyboard, my_subs_keyboard
from bot.navigation import show_screen
from bot.texts import aware as _aware, bq, format_gb as _format_gb, format_msk as _format_msk, trial_days
from database.models import Subscription, User
from database.repository import Repository
from services.referral import (
    ReferralError,
    attach_referrer,
    parse_referral_start_payload,
    parse_source_start_payload,
)
from services.subscription import (
    activate_panel_subscription,
    connect_page_url,
    to_gateway_subscription_url,
)
from services.tariffs import resolve_tariff

router = Router()
logger = logging.getLogger(__name__)


def _profile_block(user: User, display_name: str | None) -> str:
    name = html.escape(display_name or user.username or "—")
    return "👤 <b>Профиль:</b>\n" + bq(
        f"📝 Имя: {name}",
        f"🆔 ID: <code>{user.telegram_id}</code>",
    )


def _tariff_title(plan_code: str) -> str:
    try:
        return resolve_tariff(plan_code).title
    except ValueError:
        return plan_code


def _subscription_card(subscription: Subscription) -> str:
    used = _format_gb(subscription.traffic_used_bytes or 0)
    limit = _format_gb(subscription.traffic_limit_bytes)
    devices = subscription.device_limit if subscription.device_limit is not None else "∞"
    lines = [
        f"💎 Тариф: {html.escape(_tariff_title(subscription.plan))}",
        f"📊 Трафик: {used} / {limit} ГБ",
        f"📱 Устройств: до {devices}",
    ]
    lines.append(f"📅 До: {_format_msk(subscription.expires_at)}")
    return "📦 <b>Подписка</b>\n" + bq(*lines)


def _menu_text(
    user: User,
    subscriptions: list[Subscription],
    display_name: str | None,
    trial_available: bool = False,
) -> str:
    """Short home screen: profile + one-line subscription status. Detailed
    subscription cards live under «Мои подписки»."""
    sections = [_profile_block(user, display_name)]
    if not subscriptions:
        if trial_available:
            sections.append(
                f"🎁 Вам доступен <b>бесплатный пробный период — {trial_days()}</b>.\n"
                "Нажмите «🎁 Активировать пробный период» — ссылка придёт сразу, без оплаты."
            )
        else:
            sections.append(
                "🔑 Активной подписки нет.\n"
                "Нажмите «🛒 Купить подписку» — ссылка придёт автоматически после оплаты."
            )
    else:
        nearest = min(subscriptions, key=lambda s: s.expires_at)
        word = _plural_subs(len(subscriptions))
        sections.append(
            f"✅ У вас <b>{len(subscriptions)}</b> {word}\n"
            f"📅 Ближайшее окончание: {_format_msk(nearest.expires_at)}\n\n"
            "Подключение и детали — в «📋 Мои подписки»."
        )
    return "\n\n".join(sections)


def _plural_subs(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "подписка"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "подписки"
    return "подписок"


def _my_subs_text(subscriptions: list[Subscription]) -> str:
    if not subscriptions:
        return (
            "📋 <b>Мои подписки</b>\n\n"
            "Активных подписок нет. Оформите тариф через «🛒 Купить подписку»."
        )
    cards = [_subscription_card(s) for s in subscriptions]
    return "📋 <b>Мои подписки</b>\n\n" + "\n\n".join(cards) + (
        "\n\n📱 Нажмите «Подключить устройство», чтобы получить ссылку и подключиться."
    )


async def _menu_state(
    session_pool: async_sessionmaker[AsyncSession],
    telegram_id: int,
    username: str | None,
    display_name: str | None = None,
) -> tuple[str, InlineKeyboardMarkup, bool]:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=telegram_id, username=username)
        subscriptions = await repo.list_active_subscriptions(user.id)
        # Anyone who never took the trial can claim it via the visible button — as
        # long as they have no active subscription right now (activating a trial
        # would otherwise replace an active plan in the same lane).
        trial_available = not subscriptions and not await repo.has_used_trial(user.id)

        text = _menu_text(user, subscriptions, display_name, trial_available=trial_available)
        has_subscription = bool(subscriptions)

    keyboard = main_menu_keyboard(has_subscription=has_subscription, trial_available=trial_available)
    return text, keyboard, has_subscription


async def _attach_referrer_from_start(
    session_pool: async_sessionmaker[AsyncSession],
    message: Message,
) -> None:
    parts = (getattr(message, "text", None) or "").split(maxsplit=1)
    ref_code = parse_referral_start_payload(parts[1] if len(parts) > 1 else None)
    if ref_code is None:
        return
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        try:
            await attach_referrer(session, user_id=user.id, ref_code=ref_code)
        except ReferralError:
            # Self-referral, unknown code or referrer already set — ignore quietly.
            return


async def _record_start_event(
    session_pool: async_sessionmaker[AsyncSession],
    message: Message,
) -> None:
    """Best-effort funnel telemetry; must never break /start."""
    parts = (getattr(message, "text", None) or "").split(maxsplit=1)
    source = parse_source_start_payload(parts[1] if len(parts) > 1 else None)
    try:
        async with session_pool() as session:
            repo = Repository(session)
            user = await repo.get_or_create_user(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
            )
            if source:
                await repo.set_user_source_if_unset(user.id, source)
            await repo.record_funnel_event(user.id, "start", meta={"source": source} if source else None)
    except Exception:  # noqa: BLE001 - telemetry only
        logger.exception("Failed to record start funnel event for telegram_id=%s", message.from_user.id)


@router.message(CommandStart())
async def start_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    # Determine first-touch BEFORE the helpers below create the user record.
    async with session_pool() as session:
        is_new_user = await Repository(session).get_user_by_telegram_id(message.from_user.id) is None
    await _attach_referrer_from_start(session_pool, message)
    await _record_start_event(session_pool, message)
    text, keyboard, _ = await _menu_state(
        session_pool=session_pool,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        display_name=getattr(message.from_user, "full_name", None),
    )
    await send_banner(
        message.bot,
        message.chat.id,
        pick_start_banner(is_new_user),
        caption=text,
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "activate_trial")
async def activate_trial_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    telegram_id = callback.from_user.id
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=telegram_id, username=callback.from_user.username)
        if await repo.list_active_subscriptions(user.id):
            await callback.answer("У вас уже есть активная подписка.", show_alert=True)
            return
        if await repo.has_used_trial(user.id):
            await callback.answer("Пробный период уже был активирован ранее.", show_alert=True)
            return
        try:
            subscription = await activate_panel_subscription(session=session, user_id=user.id, plan="trial")
        except Exception:  # noqa: BLE001 - surface a friendly retry, don't crash
            logger.exception("Failed to activate trial on button for telegram_id=%s", telegram_id)
            await callback.answer(
                "Не удалось активировать пробный период. Попробуйте через минуту или напишите в поддержку.",
                show_alert=True,
            )
            return

    # Deliver right away — the same link-first screen a buyer gets after
    # payment, not a menu the user has to dig through.
    sub_url = to_gateway_subscription_url(subscription.subscription_url) or ""
    connect_url = connect_page_url(sub_url)
    rows = []
    if connect_url:
        rows.append([InlineKeyboardButton(text="🔗 Подключить VPN", url=connect_url)])
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    text = (
        f"🎉 <b>Пробный период активирован — {trial_days()}!</b>\n\n"
        "🔗 <b>Ссылка-подписка:</b>\n"
        f"<code>{html.escape(sub_url)}</code>\n\n"
        "Нажмите «Подключить VPN» — откроется страница с приложениями и пошаговой инструкцией."
    )
    await show_screen(callback, text, InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer("Пробный период активирован! 🎉")


@router.callback_query(F.data == "profile")
async def profile_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    text, keyboard, _ = await _menu_state(
        session_pool=session_pool,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        display_name=getattr(callback.from_user, "full_name", None),
    )
    await show_screen(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "my_subs")
async def my_subs_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        subscriptions = await repo.list_active_subscriptions(user.id)
    await show_screen(callback, _my_subs_text(subscriptions), my_subs_keyboard())
    await callback.answer()
