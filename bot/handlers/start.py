import html
import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import main_menu_keyboard, my_subs_keyboard
from bot.navigation import show_screen
from bot.texts import aware as _aware, bq, format_gb as _format_gb, format_msk as _format_msk
from database.models import Subscription, User
from database.repository import Repository
from services.money import format_rub
from services.panel_gateway import PanelGatewayError
from services.referral import ReferralError, attach_referrer, parse_referral_start_payload
from services.subscription import activate_panel_subscription
from services.tariffs import resolve_premium_region, resolve_tariff

router = Router()
logger = logging.getLogger(__name__)

BANNER_PATH = "assets/banner.jpg"

# Telegram file_id of the banner after the first upload; reused so the static
# asset is uploaded at most once per process instead of on every /start.
_banner_file_id: str | None = None


def _profile_block(user: User, display_name: str | None) -> str:
    name = html.escape(display_name or user.username or "—")
    return "👤 <b>Профиль:</b>\n" + bq(
        f"📝 Имя: {name}",
        f"🆔 ID: <code>{user.telegram_id}</code>",
        f"💰 Баланс: {format_rub(user.balance)}",
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
    if subscription.tier == "premium":
        label = "💎 Premium"
        if subscription.region:
            try:
                region = resolve_premium_region(subscription.region)
                lines.append(f"📍 Локация: {region.flag} {region.title}")
            except ValueError:
                pass
    else:
        label = "🌐 Обычный"
    lines.append(f"📅 До: {_format_msk(subscription.expires_at)}")
    return f"📦 <b>{label}</b>\n" + bq(*lines)


def _menu_text(user: User, subscriptions: list[Subscription], display_name: str | None) -> str:
    """Short home screen: profile + one-line subscription status. Detailed
    subscription cards live under «Мои подписки»."""
    sections = [_profile_block(user, display_name)]
    if not subscriptions:
        sections.append(
            "🔑 Активной подписки нет.\n"
            "Нажмите «🛒 Купить подписку» — ссылка придёт автоматически после оплаты."
        )
    else:
        nearest = min(subscriptions, key=lambda s: s.expires_at)
        word = _plural_subs(len(subscriptions))
        sections.append(
            f"✅ Активных подписок: <b>{len(subscriptions)}</b> {word}\n"
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
        "\n\n📱 Нажмите «Подключить устройство», чтобы получить ссылку и QR."
    )


async def _menu_state(
    session_pool: async_sessionmaker[AsyncSession],
    telegram_id: int,
    username: str | None,
    panel_client: object | None = None,
    display_name: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=telegram_id, username=username)
        subscriptions = await repo.list_active_subscriptions(user.id)
        latest = await repo.get_latest_subscription(user.id)
        if not subscriptions and latest is None and panel_client is not None:
            try:
                trial = await activate_panel_subscription(
                    session=session,
                    user_id=user.id,
                    plan="trial",
                    panel_client=panel_client,
                )
                subscriptions = [trial]
            except PanelGatewayError:
                logger.exception("Failed to auto-activate trial for user_id=%s", user.id)

        text = _menu_text(user, subscriptions, display_name)

    return text, main_menu_keyboard(has_subscription=bool(subscriptions))


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


async def _maybe_grant_trial(
    session_pool: async_sessionmaker[AsyncSession],
    message: Message,
) -> None:
    """Best-effort: give a brand-new user a free trial subscription on first
    /start. Skipped if the user already has any subscription (active or past).
    Provisioning failures must never break /start, so they are logged, not raised."""
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        if await repo.list_active_subscriptions(user.id):
            return
        if await repo.get_latest_subscription(user.id) is not None:
            return
        try:
            await activate_panel_subscription(session=session, user_id=user.id, plan="trial")
        except Exception:  # noqa: BLE001 - trial is best-effort; never block /start
            logger.exception("Failed to grant trial for user_id=%s", user.id)


@router.message(CommandStart())
async def start_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    await _attach_referrer_from_start(session_pool, message)
    await _maybe_grant_trial(session_pool, message)
    text, keyboard = await _menu_state(
        session_pool=session_pool,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        display_name=getattr(message.from_user, "full_name", None),
    )
    global _banner_file_id
    photo = _banner_file_id if _banner_file_id else FSInputFile(BANNER_PATH)
    sent = await message.answer_photo(photo, caption=text, reply_markup=keyboard)
    if _banner_file_id is None and sent.photo:
        _banner_file_id = sent.photo[-1].file_id


@router.callback_query(F.data == "profile")
async def profile_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    text, keyboard = await _menu_state(
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
