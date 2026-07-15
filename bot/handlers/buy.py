import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers.start import _menu_state
from bot.keyboards.main_menu import (
    premium_location_keyboard,
    renew_durations_keyboard,
    renew_menu_keyboard,
    tier_plans_keyboard,
)
from bot.navigation import show_screen
from bot.texts import bq
from config import settings
from database.repository import Repository
from services.billing_api import (
    build_payment_intent,
    crypto_minor_units,
    register_cryptobot_payment,
    register_yookassa_payment,
)
from services.cryptobot import CryptoBotError, create_invoice
from services.cryptobot import is_configured as is_cryptobot_configured
from services.money import format_rub
from services.payment import PLANS, normalize_payment_plan_code
from services.tariffs import country_flag, resolve_premium_region, resolve_tariff
from services import yookassa

logger = logging.getLogger(__name__)
router = Router()

def _crypto_minor_units(amount: str) -> int:
    return crypto_minor_units(amount)


def _payment_keyboard(pay_url: str, amount: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔓 Оплатить — {amount} USDT", url=pay_url)],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


async def _edit_current_message(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    await show_screen(callback, text, reply_markup)


async def _send_callback_message(
    callback: CallbackQuery,
    bot: Bot,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if callback.message:
        await callback.message.answer(text, reply_markup=reply_markup)
    else:
        await bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)


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


def _checkout_keyboard(
    *,
    plan: str,
    region: str | None,
    balance_ok: bool,
    crypto_ok: bool,
    price_kopecks: int,
    yookassa_ok: bool = False,
    tier: str = "standard",
    balance_kopecks: int = 0,
) -> InlineKeyboardMarkup:
    suffix = f":{region}" if region else ""
    rows: list[list[InlineKeyboardButton]] = []
    if yookassa_ok:
        # Card is the primary method → first button. Creates a YooKassa payment on
        # tap, then shows its confirmation URL.
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 Оплатить картой",
                    callback_data=f"payyk:{plan}{suffix}",
                )
            ]
        )
    if balance_ok:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"💰 Оплатить с баланса — {price_kopecks // 100}₽",
                    callback_data=f"paybal:{plan}{suffix}",
                )
            ]
        )
    if crypto_ok:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔓 Оплатить криптовалютой",
                    callback_data=f"paycrypto:{plan}{suffix}",
                )
            ]
        )
    # Topup nudge only when the wallet already has money but not enough for
    # this plan; a zero balance shows no balance UI at all (user's request).
    if not balance_ok and balance_kopecks > 0:
        rows.append([InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup_menu")])
    # One step back = this tier's plan list, not the tier-select screen.
    back_callback = f"buy_tier:{tier}" if tier != "premium" else "buy_menu"
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_checkout(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
    *,
    plan: str,
    region: str | None = None,
) -> None:
    tariff = resolve_tariff(plan)
    price_kopecks = tariff.price_rub * 100

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        balance = await repo.get_balance(user.id) or 0

    region_option = resolve_premium_region(region) if region else None
    # Balance checkout: standard always; premium only for regions backed by a
    # static panel node (others need autoscaler and stay crypto-only).
    premium_static = tariff.tier == "premium" and settings.marzban_inbounds_for_region(region) is not None
    balance_ok = balance >= price_kopecks and (tariff.tier == "standard" or premium_static)
    crypto_ok = is_cryptobot_configured()
    # YooKassa card path: standard plans only for now (premium needs region/node
    # assignment which the redirect webhook does not perform).
    yookassa_ok = yookassa.is_configured() and tariff.tier == "standard"

    card_lines = [
        f"💎 Тариф: {tariff.title}",
        f"💵 Стоимость: {tariff.price_rub}₽",
    ]
    if region_option is not None:
        card_lines.append(f"📍 Локация: {region_option.flag} {region_option.title}")
    # A zero balance is noise on the payment screen — show the wallet only
    # when there is actually money on it.
    if balance > 0:
        card_lines.append(f"💳 Ваш баланс: {format_rub(balance)}")

    sections = ["💳 <b>Оплата тарифа</b>\n\n" + bq(*card_lines)]
    if yookassa_ok or balance_ok or crypto_ok:
        sections.append("Выберите способ оплаты:")
        if yookassa_ok:
            sections.append(
                "💳 <i>Картой (рекомендуем):</i> нажмите «Оплатить картой» — откроется "
                "защищённая страница оплаты. После оплаты подписка придёт сюда автоматически."
            )
    elif tariff.tier == "premium":
        sections.append("⚠️ Оплата Premium временно доступна только криптовалютой, а она сейчас недоступна. Попробуйте позже.")
    elif balance > 0:
        need = price_kopecks - balance
        sections.append(f"💰 На балансе не хватает {format_rub(need)}. Пополните баланс и оплатите в один тап.")
    else:
        sections.append("⚠️ Способы оплаты временно недоступны. Попробуйте позже.")

    await _edit_current_message(
        callback,
        "\n\n".join(sections),
        _checkout_keyboard(
            plan=plan,
            region=region,
            balance_ok=balance_ok,
            crypto_ok=crypto_ok,
            price_kopecks=price_kopecks,
            yookassa_ok=yookassa_ok,
            tier=tariff.tier,
            balance_kopecks=balance,
        ),
    )
    await callback.answer()


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
        await _send_callback_message(callback, bot, "Не удалось создать счет. Попробуйте позже.")
        return

    external_invoice_id = invoice.get("invoice_id")
    pay_url = invoice.get("bot_invoice_url") or invoice.get("pay_url") or invoice.get("mini_app_invoice_url")
    if external_invoice_id is None or not pay_url:
        logger.error("CryptoBot invoice has no invoice_id or payment URL: %s", invoice)
        await _send_callback_message(callback, bot, "CryptoBot вернул некорректный счет. Напишите в поддержку.")
        return

    async with session_pool() as session:
        await register_cryptobot_payment(
            session,
            intent=intent,
            external_invoice_id=str(external_invoice_id),
        )

    card_lines = [
        f"💎 Тариф: {intent.plan.title}",
        f"💵 Стоимость: {intent.plan.price_rub}₽ ({intent.amount} USDT)",
    ]
    if intent.region is not None:
        card_lines.append(f"📍 Локация: {country_flag(intent.region.country_code)} {intent.region.title}")
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

    keyboard = _payment_keyboard(str(pay_url), intent.amount)
    await _send_callback_message(callback, bot, text, keyboard)


def _yookassa_pay_keyboard(
    pay_url: str,
    price_rub: int,
    *,
    plan: str | None = None,
    region: str | None = None,
    email_editable: bool = False,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"💳 Оплатить — {price_rub}₽", url=pay_url)]]
    if email_editable and plan:
        # The чек goes to the stored email; a typo would send it nowhere, so
        # let the buyer fix the address right from the payment screen.
        suffix = f":{region}" if region else ""
        rows.append(
            [InlineKeyboardButton(text="✏️ Изменить email для чека", callback_data=f"ykemail:{plan}{suffix}")]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class YookassaEmailInput(StatesGroup):
    email = State()


def _email_prompt_keyboard(plan: str, region: str | None = None) -> InlineKeyboardMarkup:
    # Cancel = one step back to this plan's checkout, not the buy menu.
    back = f"buy_region:{plan}:{region}" if region else f"buy:{plan}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data=back)]])


async def _create_yookassa_invoice(
    *,
    telegram_id: int,
    username: str | None,
    session_pool: async_sessionmaker[AsyncSession],
    plan: str,
    region: str | None,
    email: str | None,
    send,
) -> None:
    async with session_pool() as session:
        intent = await build_payment_intent(
            session,
            telegram_id=telegram_id,
            username=username,
            plan=plan,
            region=region,
        )

    try:
        payment = await yookassa.create_payment(
            amount_kopecks=intent.plan.price_rub * 100,
            description=intent.description,
            metadata={"user_id": intent.user_id, "plan": intent.plan.code},
            receipt_email=email,
        )
    except yookassa.YooKassaError:
        logger.exception("Failed to create YooKassa payment for user_id=%s plan=%s", intent.user_id, plan)
        await send("Не удалось создать платёж. Попробуйте позже.", None)
        return

    payment_id = payment.get("id")
    pay_url = yookassa.confirmation_url(payment)
    if not payment_id or not pay_url:
        logger.error("YooKassa payment missing id or confirmation_url: %s", payment)
        await send("ЮKassa вернула некорректный платёж. Напишите в поддержку.", None)
        return

    async with session_pool() as session:
        await register_yookassa_payment(session, intent=intent, external_payment_id=str(payment_id))

    receipt_line = f"🧾 Чек придёт на {email}\n" if email else ""
    text = (
        "💳 <b>Оплата картой</b>\n\n"
        + bq(
            f"💎 Тариф: {intent.plan.title}",
            f"💵 Стоимость: {intent.plan.price_rub}₽",
        )
        + "\n\nНажмите кнопку ниже и оплатите на защищённой странице.\n"
        + receipt_line
        + "Ссылка-подписка придёт автоматически в течение минуты после оплаты."
    )
    await send(
        text,
        _yookassa_pay_keyboard(
            pay_url,
            intent.plan.price_rub,
            plan=plan,
            region=region,
            email_editable=bool(email),
        ),
    )


PREMIUM_SOON_TEXT = (
    "💎 <b>Premium — скоро</b>\n\n"
    "<blockquote>"
    "🔒 Мало соседей на ноде (низкая плотность)\n"
    "📌 Стабильный IP в выбранной стране\n"
    "⚡️ Максимальная скорость"
    "</blockquote>\n\n"
    "Сейчас доступен <b>Обычный</b> тариф с несколькими локациями. "
    "Premium запустим с отдельными разгруженными нодами."
)

TIER_TEXTS = {
    "standard": (
        "🚀 <b>Обычный тариф</b>\n\n"
        "<blockquote>"
        "🌍 Несколько локаций (🇺🇸 США, 🇳🇱 Нидерланды)\n"
        "🔀 Переключение между странами прямо в приложении\n"
        "📊 До 150 ГБ трафика в месяц\n"
        "📱 До 3–5 устройств"
        "</blockquote>\n\n"
        "Выберите срок:"
    ),
}


@router.callback_query(F.data == "buy_menu")
async def buy_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    # Single tier for now — skip the tier picker and go straight to durations.
    await state.clear()  # drop any pending email-input state
    await _edit_current_message(callback, TIER_TEXTS["standard"], tier_plans_keyboard("standard"))
    await callback.answer()


@router.callback_query(F.data.startswith("buy_tier:"))
async def buy_tier_handler(callback: CallbackQuery) -> None:
    tier = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    if tier == "premium":
        # Stale keyboards from old messages may still carry the premium button.
        await _edit_current_message(callback, PREMIUM_SOON_TEXT, tier_plans_keyboard("standard"))
        await callback.answer()
        return
    text = TIER_TEXTS.get(tier)
    if text is None:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return
    await _edit_current_message(callback, text, tier_plans_keyboard(tier))
    await callback.answer()


@router.callback_query(F.data == "renew_menu")
async def renew_menu_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        subscriptions = await repo.list_active_subscriptions(user.id)

    if not subscriptions:
        await _edit_current_message(
            callback,
            "🔄 <b>Продление</b>\n\nУ вас нет активных подписок. Оформите тариф через «🛒 Купить тариф».",
            tier_plans_keyboard("standard"),
        )
        await callback.answer()
        return

    text = "🔄 <b>Продление</b>\n\nВыберите подписку, которую хотите продлить:"
    await _edit_current_message(callback, text, renew_menu_keyboard(subscriptions))
    await callback.answer()


@router.callback_query(F.data.startswith("renew_sub:"))
async def renew_sub_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    try:
        sub_id = int(callback.data.split(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer("Подписка не найдена", show_alert=True)
        return
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(callback.from_user.id)
        subscription = await repo.get_subscription(sub_id) if user else None
        if user is None or subscription is None or subscription.user_id != user.id:
            await callback.answer("Подписка не найдена", show_alert=True)
            return
        tier, region = subscription.tier, subscription.region

    label = "💎 Premium" if tier == "premium" else "🌐 Обычный"
    text = f"🔄 <b>Продление: {label}</b>\n\nВыберите срок — он добавится к текущему:"
    await _edit_current_message(callback, text, renew_durations_keyboard(tier, region))
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery, session_pool: async_sessionmaker[AsyncSession]) -> None:
    text, keyboard, _ = await _menu_state(
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
        # Premium sales are paused until dedicated low-density nodes exist.
        await _edit_current_message(callback, PREMIUM_SOON_TEXT, tier_plans_keyboard("standard"))
        await callback.answer()
        return

    await _show_checkout(callback, session_pool, plan=plan)


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

    # Premium sales are paused until dedicated low-density nodes exist.
    await _edit_current_message(callback, PREMIUM_SOON_TEXT, tier_plans_keyboard("standard"))
    await callback.answer()


@router.callback_query(F.data.startswith("paycrypto:"))
async def pay_crypto_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    parts = callback.data.split(":", maxsplit=2) if callback.data else []
    raw_plan = parts[1] if len(parts) >= 2 else ""
    raw_region = parts[2] if len(parts) == 3 else None
    try:
        plan = normalize_payment_plan_code(raw_plan)
    except ValueError:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    region: str | None = None
    if raw_region is not None:
        try:
            region = resolve_premium_region(raw_region).code
        except ValueError:
            await callback.answer("Локация не найдена", show_alert=True)
            return

    if not is_cryptobot_configured():
        await callback.answer("Оплата криптовалютой сейчас недоступна.", show_alert=True)
        return

    await callback.answer()
    await _create_payment_invoice(callback, bot, session_pool, plan=plan, region=region)


@router.callback_query(F.data.startswith("payyk:"))
async def pay_yookassa_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
    state: FSMContext,
) -> None:
    parts = callback.data.split(":", maxsplit=2) if callback.data else []
    raw_plan = parts[1] if len(parts) >= 2 else ""
    raw_region = parts[2] if len(parts) == 3 else None
    try:
        plan = normalize_payment_plan_code(raw_plan)
    except ValueError:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    region: str | None = None
    if raw_region is not None:
        try:
            region = resolve_premium_region(raw_region).code
        except ValueError:
            await callback.answer("Локация не найдена", show_alert=True)
            return

    if not yookassa.is_configured():
        await callback.answer("Оплата картой сейчас недоступна.", show_alert=True)
        return

    await callback.answer()

    async with session_pool() as session:
        user = await Repository(session).get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        stored_email = user.email

    # 54-ФЗ: if receipts are on, we form the чек ourselves, and we don't yet have
    # the buyer's email, ask once. In on-page mode YooKassa collects it instead.
    if settings.YOOKASSA_RECEIPT_ENABLED and not settings.YOOKASSA_COLLECT_EMAIL_ON_PAGE and not stored_email:
        await state.set_state(YookassaEmailInput.email)
        await state.update_data(plan=plan, region=region)
        text = (
            "📧 <b>Email для чека</b>\n\n"
            + bq(
                "По закону (54-ФЗ) на оплату картой формируется чек.",
                "Он придёт вам на email.",
            )
            + "\n\nОтправьте ваш email одним сообщением (например, <code>name@mail.ru</code>)."
        )
        await _send_callback_message(callback, bot, text, _email_prompt_keyboard(plan, region))
        return

    await _create_yookassa_invoice(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session_pool=session_pool,
        plan=plan,
        region=region,
        email=stored_email,
        send=lambda text, kb: _send_callback_message(callback, bot, text, kb),
    )


@router.callback_query(F.data.startswith("ykemail:"))
async def yookassa_change_email_handler(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":", maxsplit=2) if callback.data else []
    raw_plan = parts[1] if len(parts) >= 2 else ""
    raw_region = parts[2] if len(parts) == 3 else None
    try:
        plan = normalize_payment_plan_code(raw_plan)
    except ValueError:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    region: str | None = None
    if raw_region is not None:
        try:
            region = resolve_premium_region(raw_region).code
        except ValueError:
            await callback.answer("Локация не найдена", show_alert=True)
            return

    await state.set_state(YookassaEmailInput.email)
    await state.update_data(plan=plan, region=region)
    text = (
        "✏️ <b>Новый email для чека</b>\n\n"
        "Отправьте адрес одним сообщением (например, <code>name@mail.ru</code>) — "
        "мы сохраним его и выставим счёт заново."
    )
    await _send_callback_message(callback, bot, text, _email_prompt_keyboard(plan, region))
    await callback.answer()


@router.message(YookassaEmailInput.email)
async def yookassa_email_message_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    email = (message.text or "").strip()
    if not _EMAIL_RE.match(email) or len(email) > 320:
        data = await state.get_data()
        await message.answer(
            "Это не похоже на email. Отправьте адрес вида <code>name@mail.ru</code>.",
            reply_markup=_email_prompt_keyboard(str(data.get("plan") or ""), data.get("region")),
        )
        return

    data = await state.get_data()
    await state.clear()
    plan = data.get("plan")
    region = data.get("region")
    if not plan:
        await message.answer("Сессия оплаты истекла. Откройте тариф заново через «🛒 Купить».")
        return

    async with session_pool() as session:
        user = await Repository(session).get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        await Repository(session).update_user(user.id, email=email)

    await _create_yookassa_invoice(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        session_pool=session_pool,
        plan=plan,
        region=region,
        email=email,
        send=lambda text, kb: message.answer(text, reply_markup=kb),
    )
