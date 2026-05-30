import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from database.repository import Repository
from services.qrcode import generate_qr_png_bytes
from services.wireguard import WireGuardError, rotate_user_key

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "get_key", flags={"subscription_required": True})
async def get_key_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        if user is None:
            await callback.answer("Пользователь не найден. Нажмите /start.", show_alert=True)
            return

        try:
            _, config_text = await rotate_user_key(session=session, user_id=user.id)
        except WireGuardError:
            logger.exception("Could not provide WireGuard key for user_id=%s", user.id)
            await callback.answer("Не удалось подготовить ключ. Напишите в поддержку.", show_alert=True)
            return

    qr_bytes = await generate_qr_png_bytes(config_text)
    filename = f"wireguard_{callback.from_user.id}.conf"
    if callback.message:
        await callback.message.answer_document(
            BufferedInputFile(config_text.encode("utf-8"), filename=filename),
            caption="Ваш WireGuard-конфиг.",
        )
        await callback.message.answer_photo(
            BufferedInputFile(qr_bytes, filename="wireguard_qr.png"),
            caption="QR-код для импорта в WireGuard.",
            reply_markup=back_to_menu_keyboard(),
        )
    await callback.answer()
