import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers.start import _menu_state
from bot.keyboards.main_menu import premium_location_keyboard, tier_plans_keyboard, tier_select_keyboard
from bot.navigation import show_screen
from bot.texts import bq
from database.repository import Repository
from services.billing_api import build_payment_intent, crypto_minor_units, register_cryptobot_payment
from services.cryptobot import CryptoBotError, create_invoice
from services.payment import PLANS, normalize_payment_plan_code
from services.tariffs import resolve_premium_region, resolve_tariff

logger = logging.getLogger(__name__)
router = Router()

def _crypto_minor_units(amount: str) -> int:
    return crypto_minor_units(amount)


def _payment_keyboard(
    pay_url: str,
    amount: str,
    *,
    balance_plan: str | None = None,
    balance_price_kopecks: int = 0,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🔓 Оплатить — {amount} USDT", url=pay_url)]]
    if balance_plan is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"💰 Оплатить с баланса — {balance_price_kopecks // 100}₽",
                    callback_data=f"paybal:{balance_plan}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_current_message(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    await show_screen(callback, text, reply_markup)


def _premium_location_text(plan: str) -> str:
    plan_data = PLANS[plan]
    return (
        "🌍 <b>Выбор локации</b>\n\n"
        + bq(
            f"💎 Тариф: {plan_data['title']}",
            f"💵 Стоимость: {plan_data['rub_amount']}₽",
        )
        + "\n\nВыберите локацию premium-ноды. Если в регионе нет свободного места, "
        "сервер будет поднят автоматически (~2 минуты после оплаты)."
    )


async def _create_payment_invoice(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
    *,
    plan: str,
    region: str | None = None,
) -> None:
    async with session_pool() as session:
        intent = await build_payment_intent(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            plan=plan,
            region=region,
        )

        try:
            invoice = await create_invoice(
                amount=intent.amount,
                payload=intent.payload,
                description=intent.description,
                asset=intent.asset,
            )
        except CryptoBotError:
            logger.exception("Failed to create CryptoBot invoice for user_id=%s plan=%s", intent.user_id, plan)
            await callback.answer("Не удалось создать счет. Попробуйте позже.", show_alert=True)
            return

        external_invoice_id = invoice.get("invoice_id")
        pay_url = invoice.get("bot_invoice_url") or invoice.get("pay_url") or invoice.get("mini_app_invoice_url")
        if external_invoice_id is None or not pay_url:
            logger.error("CryptoBot invoice has no invoice_id or payment URL: %s", invoice)
            await callback.answer("CryptoBot вернул некорректный счет. Напишите в поддержку.", show_alert=True)
            return

        await register_cryptobot_payment(
            session,
            intent=intent,
            external_invoice_id=str(external_invoice_id),
        )

        price_kopecks = intent.plan.price_rub * 100
        balance = await Repository(session).get_balance(intent.user_id) or 0
        balance_plan = (
            intent.plan.code
            if intent.plan.tier == "standard" and balance >= price_kopecks
            else None
        )

    card_lines = [
        f"💎 Тариф: {intent.plan.title}",
        f"💵 Стоимость: {intent.plan.price_rub}₽ ({intent.amount} USDT)",
    ]
    if intent.region is not None:
        card_lines.append(f"🌍 Локация: {intent.region.title}")
    tail = (
        "После оплаты premium-нода закрепляется автоматически. Если свободной нет, подготовка займёт около 2 минут."
        if intent.plan.tier == "premium"
        else "Ссылка-подписка придёт автоматически в течение минуты после оплаты."
    )
    text = (
        "💳 <b>Оплата тарифа</b>\n\n"
        + bq(*card_lines)
        + "\n\nНажмите кнопку ниже, выберите валюту (USDT/TON/BTC) и оплатите.\n"
        + tail
    )

    keyboard = _payment_keyboard(
        str(pay_url),
        intent.amount,
        balance_plan=balance_plan,
        balance_price_kopecks=price_kopecks,
    )
    if callback.message:
        await callback.message.answer(text, reply_markup=keyboard)
    else:
        await bot.send_message(callback.from_user.id, text, reply_markup=keyboard)
    await callback.answer()


BUY_MENU_TEXT = (
    "🛒 <b>Выбор тарифа</b>\n\n"
    "<blockquote>"
    "🚀 <b>Обычный</b> — общий пул серверов, лучшая цена.\n"
    "💎 <b>Premium</b> — меньше соседей на ноде, выбор локации, выше скорость."
    "</blockquote>\n\n"
    "Выберите вариант — ниже появятся сроки и цены."
)

TIER_TEXTS = {
    "standard": (
        "🚀 <b>Обычный тариф</b>\n\n"
        "<blockquote>"
        "🌐 Общий пул серверов\n"
        "📊 До 150 ГБ трафика в месяц\n"
        "📱 До 3–5 устройств"
        "</blockquote>\n\n"
        "Выберите срок:"
    ),
    "premium": (
        "💎 <b>Premium тариф</b>\n\n"
        "<blockquote>"
        "🌍 Выбор локации (Амстердам, Франкфурт, Варшава)\n"
        "⚡️ Меньше соседей — стабильнее скорость\n"
        "📊 До 300 ГБ трафика в месяц\n"
        "📱 До 5–8 устройств"
        "</blockquote>\n\n"
        "Выберите срок:"
    ),
}


@router.callback_query(F.data == "buy_menu")
async def buy_menu_handler(callback: CallbackQuery) -> None:
    await _edit_current_message(callback, BUY_MENU_TEXT, tier_select_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("buy_tier:"))
async def buy_tier_handler(callback: CallbackQuery) -> None:
    tier = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    text = TIER_TEXTS.get(tier)
    if text is None:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return
    await _edit_current_message(callback, text, tier_plans_keyboard(tier))
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    text, keyboard = await _menu_state(
        session_pool=session_pool,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        display_name=getattr(callback.from_user, "full_name", None),
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
