import html
import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import active_subscription_keyboard, landing_keyboard
from bot.texts import aware as _aware, bq, format_gb as _format_gb, format_msk as _format_msk
from database.models import Subscription, User
from database.repository import Repository
from services.money import format_rub
from services.panel_gateway import PanelGatewayError, is_panel_configured
from services.referral import ReferralError, attach_referrer, parse_referral_start_payload
from services.subscription import activate_panel_subscription
from services.tariffs import resolve_tariff

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


def _menu_text(user: User, subscription: Subscription | None, display_name: str | None) -> str:
    sections = [_profile_block(user, display_name)]

    if subscription is None:
        sections.append(
            "🔑 <b>Подписка:</b> не активна\n\n"
            "Выберите тариф ниже — ссылка-подписка придёт автоматически после оплаты."
        )
        return "\n\n".join(sections)

    if subscription.subscription_url:
        sections.append(
            "🔑 <b>Ваша подписка:</b>\n"
            f"<code>{html.escape(subscription.subscription_url)}</code>"
        )

    used = _format_gb(subscription.traffic_used_bytes or 0)
    limit = _format_gb(subscription.traffic_limit_bytes)
    devices = subscription.device_limit if subscription.device_limit is not None else "∞"
    sections.append(
        "📦 <b>Информация о тарифе:</b>\n"
        + bq(
            f"💎 Тариф: {html.escape(_tariff_title(subscription.plan))}",
            f"📊 Трафик: {used} / {limit} ГБ",
            f"📱 Устройств: до {devices}",
        )
    )
    sections.append(f"📅 <b>Срок действия:</b> {_format_msk(subscription.expires_at)}")
    return "\n\n".join(sections)


def _remnawave_configured() -> bool:
    return is_panel_configured()


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
        subscription = await repo.get_active_subscription(user.id)
        latest = subscription or await repo.get_latest_subscription(user.id)
        if subscription is None and latest is None and (panel_client is not None or _remnawave_configured()):
            try:
                subscription = await activate_panel_subscription(
                    session=session,
                    user_id=user.id,
                    plan="trial",
                    panel_client=panel_client,
                )
            except PanelGatewayError:
                logger.exception("Failed to auto-activate trial for user_id=%s", user.id)

        text = _menu_text(user, subscription, display_name)

    if subscription is None:
        return text, landing_keyboard()
    return text, active_subscription_keyboard()


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


@router.message(CommandStart())
async def start_handler(message: Message, session_pool: async_sessionmaker[AsyncSession]) -> None:
    await _attach_referrer_from_start(session_pool, message)
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
