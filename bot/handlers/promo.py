"""Promo code redemption.

Promo entry used to live behind the wallet screen, which is where the balance
system put it. With the wallet gone, redemption stands on its own: /promo, plus
the original ``promo_enter`` callback so any keyboard still carrying that button
keeps working.

Only subscription grants remain — a code hands over days of access directly.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from bot.keyboards.main_menu import back_to_menu_keyboard
from database.repository import Repository
from services import billing_api, promo

logger = logging.getLogger(__name__)
router = Router()

PROMPT = (
    "🎟 <b>Промокод</b>\n\n"
    "Отправьте промокод одним сообщением."
)


class PromoInput(StatesGroup):
    code = State()


def _promo_error_text(exc: promo.PromoError) -> str:
    if isinstance(exc, promo.PromoNotFoundError):
        return "Такого промокода нет. Проверьте написание."
    if isinstance(exc, promo.PromoExpiredError):
        return "Срок действия промокода истёк."
    if isinstance(exc, promo.PromoInactiveError):
        return "Промокод отключён."
    if isinstance(exc, promo.PromoExhaustedError):
        return "Промокод уже исчерпан."
    if isinstance(exc, promo.PromoUserLimitError):
        return "Вы уже использовали этот промокод."
    return "Промокод не подошёл."


@router.callback_query(F.data == "promo_enter")
async def promo_enter_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoInput.code)
    if callback.message is not None:
        await callback.message.edit_text(PROMPT, reply_markup=back_to_menu_keyboard())
    await callback.answer()


@router.message(Command("promo"))
async def promo_command(message: Message, state: FSMContext) -> None:
    await state.set_state(PromoInput.code)
    await message.answer(PROMPT, reply_markup=back_to_menu_keyboard())


@router.message(PromoInput.code)
async def promo_code_message_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    code = (message.text or "").strip()
    if not code:
        await message.answer("Отправьте промокод текстом или вернитесь в меню.", reply_markup=back_to_menu_keyboard())
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        try:
            result = await billing_api.redeem_promo(session, user_id=user.id, code=code)
        except promo.PromoError as exc:
            await message.answer(_promo_error_text(exc), reply_markup=back_to_menu_keyboard())
            return

    await state.clear()
    await message.answer(
        f"🎉 Промокод применён: подписка на {result.granted_days} дней уже активна.\n\n"
        "Откройте «Подключить VPN» — конфигурация готова.",
        reply_markup=back_to_menu_keyboard(),
    )
