import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from database.repository import Repository
from services.payment import PLANS
from services.qrcode import generate_qr_png_bytes
from services.subscription import activate_subscription
from services.wireguard import WireGuardError, ensure_user_peer

logger = logging.getLogger(__name__)
router = Router()

TEST_KEY_PLAN = "basic" if "basic" in PLANS else "1m"


@router.message(Command("test_key"))
async def test_key_handler(
    message: Message,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user.id not in settings.admin_ids_list:
        await message.answer("Команда доступна только администраторам")
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
