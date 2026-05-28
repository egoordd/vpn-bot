import logging
from decimal import Decimal, ROUND_HALF_UP

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers.start import LANDING_TEXT, _menu_state
from bot.keyboards.main_menu import landing_keyboard
from database.repository import Repository
from services.cryptobot import CryptoBotError, create_invoice
from services.payment import PLANS, create_invoice_payload

logger = logging.getLogger(__name__)
router = Router()

BUY_CALLBACKS = {"buy:1m", "buy:3m", "buy:6m"}


def _crypto_minor_units(amount: str) -> int:
    return int((Decimal(amount) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _payment_keyboard(pay_url: str, amount: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔓 Оплатить — {amount} USDT", url=pay_url)],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
        ]
    )


async def _edit_current_message(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    if not callback.message:
        return

    if callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup)


@router.callback_query(F.data == "buy_menu")
async def buy_menu_handler(callback: CallbackQuery) -> None:
    await _edit_current_message(callback, LANDING_TEXT, landing_keyboard())
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    text, keyboard = await _menu_state(
        session_pool=session_pool,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    await _edit_current_message(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.in_(BUY_CALLBACKS))
async def buy_plan_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    plan = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    plan_data = PLANS.get(plan)
    if plan_data is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        payload = create_invoice_payload(user_id=user.id, plan=plan)
        amount = str(plan_data["crypto_amount"])
        description = str(plan_data["description"])

        try:
            invoice = await create_invoice(
                amount=amount,
                payload=payload,
                description=description,
                asset="USDT",
            )
        except CryptoBotError:
            logger.exception("Failed to create CryptoBot invoice for user_id=%s plan=%s", user.id, plan)
            await callback.answer("Не удалось создать счет. Попробуйте позже.", show_alert=True)
            return

        external_invoice_id = invoice.get("invoice_id")
        pay_url = invoice.get("bot_invoice_url") or invoice.get("pay_url") or invoice.get("mini_app_invoice_url")
        if external_invoice_id is None or not pay_url:
            logger.error("CryptoBot invoice has no invoice_id or payment URL: %s", invoice)
            await callback.answer("CryptoBot вернул некорректный счет. Напишите в поддержку.", show_alert=True)
            return

        await repo.create_cryptobot_payment(
            user_id=user.id,
            amount=_crypto_minor_units(amount),
            external_invoice_id=str(external_invoice_id),
            invoice_payload=payload,
            plan=plan,
        )

    rub_amount = int(plan_data["rub_amount"])
    label = str(plan_data["label"])
    text = (
        f"💳 Оплата тарифа: {label} — {rub_amount}₽\n\n"
        "Нажми кнопку ниже, выбери валюту (USDT/TON/BTC) и оплати.\n"
        "Ключ придёт автоматически в течение минуты после оплаты."
    )

    if callback.message:
        await callback.message.answer(text, reply_markup=_payment_keyboard(str(pay_url), amount))
    else:
        await bot.send_message(callback.from_user.id, text, reply_markup=_payment_keyboard(str(pay_url), amount))
    await callback.answer()
