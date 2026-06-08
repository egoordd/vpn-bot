import logging

from aiogram import Bot
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from database.repository import Repository
from scheduler.tasks import traffic_sync
from services.panel_gateway import PanelGatewayError, get_panel_gateway
from services.qrcode import generate_qr_png_bytes
from services.subscription import activate_subscription
from services.wireguard import WireGuardError, ensure_user_peer

logger = logging.getLogger(__name__)
router = Router()

TEST_KEY_PLAN = "standard_1m"


def _is_admin(message: Message) -> bool:
    return message.from_user.id in settings.admin_ids_list


async def _reject_non_admin(message: Message) -> bool:
    if _is_admin(message):
        return False
    await message.answer("Команда доступна только администраторам")
    return True


def _format_gb(value: int | None) -> str:
    if value is None:
        return "без лимита"
    return f"{value / 1024**3:.1f} ГБ"


def _parse_telegram_id_arg(message: Message) -> int:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        return message.from_user.id
    return int(parts[1].strip())


@router.message(Command("test_key"))
async def test_key_handler(
    message: Message,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    if await _reject_non_admin(message):
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        await activate_subscription(session=session, user_id=user.id, plan=TEST_KEY_PLAN)

        try:
            _, config_text = await ensure_user_peer(session=session, user_id=user.id)
        except WireGuardError:
            logger.exception("WireGuard provisioning failed for admin test_key user_id=%s", user.id)
            await message.answer("Не удалось подготовить ключ. Напишите в поддержку.")
            return

    qr_bytes = await generate_qr_png_bytes(config_text)
    filename = f"wireguard_{message.from_user.id}.conf"
    await message.answer_document(
        BufferedInputFile(config_text.encode("utf-8"), filename=filename),
        caption="Ваш WireGuard-конфиг.",
    )
    await message.answer_photo(
        BufferedInputFile(qr_bytes, filename="wireguard_qr.png"),
        caption="QR-код для импорта в WireGuard.",
    )


@router.message(Command("sync_traffic"))
async def sync_traffic_handler(
    message: Message,
    session_pool: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    if await _reject_non_admin(message):
        return

    try:
        synced_count = await traffic_sync(bot=bot, session_pool=session_pool)
    except Exception:
        logger.exception("Manual traffic sync failed")
        await message.answer("Не удалось синхронизировать трафик. Смотрите логи.")
        return

    await message.answer(f"Синхронизация трафика завершена. Обновлено подписок: {synced_count}.")


@router.message(Command("panel_user"))
async def panel_user_handler(
    message: Message,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    if await _reject_non_admin(message):
        return

    try:
        telegram_id = _parse_telegram_id_arg(message)
    except ValueError:
        await message.answer("Использование: /panel_user <telegram_id>")
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(telegram_id)
        if user is None:
            await message.answer(f"Пользователь {telegram_id} не найден в БД.")
            return
        subscription = await repo.get_latest_subscription(user.id)

    if subscription is None:
        await message.answer(f"У пользователя {telegram_id} нет подписок.")
        return
    if not subscription.panel_username:
        await message.answer(f"Последняя подписка пользователя {telegram_id} не привязана к панели.")
        return

    try:
        panel_user = await get_panel_gateway().get_user(subscription.panel_username)
    except PanelGatewayError:
        logger.exception(
            "Failed to fetch panel user for telegram_id=%s panel_username=%s",
            telegram_id,
            subscription.panel_username,
        )
        await message.answer("Не удалось получить пользователя из панели. Смотрите логи.")
        return

    text = (
        f"Telegram ID: {telegram_id}\n"
        f"Panel username: {panel_user.username}\n"
        f"Status: {panel_user.status}\n"
        f"Traffic: {_format_gb(panel_user.used_traffic_bytes)} / {_format_gb(panel_user.traffic_limit_bytes)}\n"
        f"Devices: {panel_user.device_limit or 'без лимита'}\n"
        f"Expires: {panel_user.expire_at}\n"
        f"Sub URL: {panel_user.subscription_url}"
    )
    await message.answer(text)
