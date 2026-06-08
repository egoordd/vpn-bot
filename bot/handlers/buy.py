import logging
from decimal import Decimal, ROUND_HALF_UP

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers.start import LANDING_TEXT, _menu_state
from bot.keyboards.main_menu import landing_keyboard, premium_location_keyboard
from database.repository import Repository
from services.cryptobot import CryptoBotError, create_invoice
from services.payment import PLANS, create_invoice_payload, normalize_payment_plan_code
from services.tariffs import resolve_premium_region, resolve_tariff

logger = logging.getLogger(__name__)
router = Router()

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

    if getattr(callback.message, "photo", None):
        await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup)


def _premium_location_text(plan: str) -> str:
    plan_data = PLANS[plan]
    return (
        f"🌍 {plan_data['title']}\n"
        f"Стоимость: {plan_data['rub_amount']}₽\n\n"
        "Выбери локацию premium-ноды. "
        "Если в выбранном регионе нет свободного места, мы поднимем сервер автоматически; "
        "обычно подготовка занимает около 2 минут после оплаты."
    )


async def _create_payment_invoice(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
    *,
    plan: str,
    region: str | None = None,
) -> None:
    plan_data = PLANS[plan]
    tariff = resolve_tariff(plan)
    region_option = resolve_premium_region(region) if region else None

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        payload = create_invoice_payload(user_id=user.id, plan=plan, region=region)
        amount = str(plan_data["crypto_amount"])
        description = str(plan_data["description"])
        if region_option is not None:
            description = f"{description}: {region_option.title}"

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
    title = str(plan_data["title"])
    lines = [
        f"💳 Оплата тарифа: {title} — {rub_amount}₽",
    ]
    if region_option is not None:
        lines.append(f"Локация: {region_option.title}")
    lines.append("")
    lines.append("Нажми кнопку ниже, выбери валюту (USDT/TON/BTC) и оплати.")
    if tariff.tier == "premium":
        lines.append("После оплаты закрепим premium-ноду. Если свободной нет, подготовка займёт около 2 минут.")
    else:
        lines.append("Ссылка-подписка придёт автоматически в течение минуты после оплаты.")
    text = "\n".join(lines)

    if callback.message:
        await callback.message.answer(text, reply_markup=_payment_keyboard(str(pay_url), amount))
    else:
        await bot.send_message(callback.from_user.id, text, reply_markup=_payment_keyboard(str(pay_url), amount))
    await callback.answer()


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


@router.callback_query(F.data.startswith("buy:"))
async def buy_plan_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    raw_plan = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    try:
        plan = normalize_payment_plan_code(raw_plan)
    except ValueError:
        await callback.answer("Тариф не найден", show_alert=True)
        return
    tariff = resolve_tariff(plan)

    if tariff.tier == "premium":
        await _edit_current_message(callback, _premium_location_text(plan), premium_location_keyboard(plan))
        await callback.answer()
        return

    await _create_payment_invoice(callback, bot, session_pool, plan=plan)


@router.callback_query(F.data.startswith("buy_region:"))
async def buy_region_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    parts = callback.data.split(":", maxsplit=2) if callback.data else []
    if len(parts) != 3:
        await callback.answer("Локация не найдена", show_alert=True)
        return

    raw_plan, raw_region = parts[1], parts[2]
    try:
        plan = normalize_payment_plan_code(raw_plan)
        tariff = resolve_tariff(plan)
        if tariff.tier != "premium":
            raise ValueError("not premium")
        region = resolve_premium_region(raw_region).code
    except ValueError:
        await callback.answer("Локация не найдена", show_alert=True)
        return

    await _create_payment_invoice(callback, bot, session_pool, plan=plan, region=region)
