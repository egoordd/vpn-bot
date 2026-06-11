import logging
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import active_subscription_keyboard, landing_keyboard
from database.repository import Repository
from services.panel_gateway import PanelGatewayError, is_panel_configured
from services.subscription import activate_panel_subscription

router = Router()
logger = logging.getLogger(__name__)

BANNER_PATH = "assets/banner.jpg"

# Telegram file_id of the banner after the first upload; reused so the static
# asset is uploaded at most once per process instead of on every /start.
_banner_file_id: str | None = None

LANDING_TEXT = (
    "<b>UnLock</b>\n"
    "Быстрый VPN за копейки\n\n"
    "Выбери тариф, оплати через CryptoBot и получи ссылку-подписку автоматически."
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _active_text(expires_at: datetime) -> str:
    return (
        "<b>UnLock</b>\n"
        f"✅ Подписка активна до {_aware(expires_at):%d.%m.%Y %H:%M} UTC\n\n"
        "Можно подключить устройство или продлить доступ."
    )


def _remnawave_configured() -> bool:
    return is_panel_configured()


async def _menu_state(
    session_pool: async_sessionmaker[AsyncSession],
    telegram_id: int,
    username: str | None,
    panel_client: object | None = None,
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
    global _banner_file_id
    photo = _banner_file_id if _banner_file_id else FSInputFile(BANNER_PATH)
    sent = await message.answer_photo(photo, caption=text, reply_markup=keyboard)
    if _banner_file_id is None and sent.photo:
        _banner_file_id = sent.photo[-1].file_id
