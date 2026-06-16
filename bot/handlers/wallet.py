import logging
import uuid
from typing import Awaitable, Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_wallet_keyboard, topup_keyboard, wallet_keyboard
from bot.navigation import show_screen
from bot.texts import bq, format_msk
from config import settings
from database.repository import Repository
from services import billing_api, promo, wallet
from services.cryptobot import CryptoBotError, create_invoice
from services.money import format_rub
from services.panel_gateway import PanelGatewayError, is_panel_configured
from services.payment import (
    MAX_TOPUP_KOPECKS,
    MIN_TOPUP_KOPECKS,
    TOPUP_PRESETS_KOPECKS,
    create_topup_payload,
    usdt_amount_for_kopecks,
)
from services.referral import build_referral_link
from services.subscription import activate_panel_subscription
from services.tariffs import resolve_premium_region, resolve_tariff

logger = logging.getLogger(__name__)
router = Router()

_KIND_LABELS = {
    wallet.KIND_DEPOSIT: "Пополнение",
    wallet.KIND_SPEND: "Оплата",
    wallet.KIND_REFERRAL_REWARD: "Реферал",
    wallet.KIND_PROMO_BONUS: "Промокод",
    wallet.KIND_REFUND: "Возврат",
    wallet.KIND_ADJUSTMENT: "Коррекция",
}

# Cached bot username (per bot id) to avoid a get_me API call on every click.
_bot_usernames: dict[int, str] = {}


class PromoInput(StatesGroup):
    code = State()


class TopupInput(StatesGroup):
    amount = State()


async def _edit_current_message(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    await show_screen(callback, text, reply_markup)


async def _bot_username(bot: Bot) -> str:
    cached = _bot_usernames.get(bot.id)
    if cached is not None:
        return cached
    me = await bot.get_me()
    username = me.username or ""
    _bot_usernames[bot.id] = username
    return username


def _wallet_text(overview: billing_api.AccountOverview) -> str:
    sections = [
        "💰 <b>Кошелёк</b>\n\n" + bq(f"💳 Баланс: <b>{overview.balance_display}</b>"),
    ]
    if overview.wallet.entries:
        entry_lines = []
        for entry in overview.wallet.entries[:5]:
            sign = "+" if entry.amount_kopecks >= 0 else "−"
            label = _KIND_LABELS.get(entry.kind, entry.kind)
            entry_lines.append(f"{sign}{format_rub(abs(entry.amount_kopecks))} — {label}")
        sections.append("📜 <b>Последние операции:</b>\n" + bq(*entry_lines))
    else:
        sections.append("📜 Операций пока нет. Пополните баланс или активируйте промокод.")
    sections.append("⚡️ Балансом можно оплачивать тарифы в один тап.")
    return "\n\n".join(sections)


@router.callback_query(F.data == "wallet")
async def wallet_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        overview = await billing_api.get_account_overview(session, user.id, wallet_history_limit=5)

    await _edit_current_message(callback, _wallet_text(overview), wallet_keyboard())
    await callback.answer()


@router.callback_query(F.data == "topup_menu")
async def topup_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = (
        "➕ <b>Пополнение баланса</b>\n\n"
        + bq(
            "💵 Счёт выставляется в USDT через CryptoBot",
            "💰 Баланс зачисляется в рублях автоматически",
        )
        + "\n\nВыберите сумму или укажите свою."
    )
    await _edit_current_message(callback, text, topup_keyboard(TOPUP_PRESETS_KOPECKS))
    await callback.answer()


@router.callback_query(F.data == "topup_custom")
async def topup_custom_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TopupInput.amount)
    text = (
        "✏️ <b>Своя сумма</b>\n\n"
        + bq(
            f"📉 Минимум: {MIN_TOPUP_KOPECKS // 100}₽",
            f"📈 Максимум: {MAX_TOPUP_KOPECKS // 100}₽",
        )
        + "\n\nОтправьте сумму в рублях одним сообщением (например, <code>250</code>)."
    )
    await _edit_current_message(callback, text, back_to_wallet_keyboard())
    await callback.answer()


@router.message(TopupInput.amount)
async def topup_amount_message_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip().replace("₽", "").replace(",", ".").replace(" ", "")
    try:
        rubles = float(raw)
    except ValueError:
        await message.answer(
            "Нужно число в рублях, например <code>250</code>.",
            reply_markup=back_to_wallet_keyboard(),
        )
        return

    amount_kopecks = int(round(rubles * 100))
    if not MIN_TOPUP_KOPECKS <= amount_kopecks <= MAX_TOPUP_KOPECKS:
        await message.answer(
            f"Сумма должна быть от {MIN_TOPUP_KOPECKS // 100}₽ до {MAX_TOPUP_KOPECKS // 100}₽.",
            reply_markup=back_to_wallet_keyboard(),
        )
        return

    await state.clear()
    await _create_topup_invoice(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        amount_kopecks=amount_kopecks,
        session_pool=session_pool,
        send=message.answer,
        on_error=lambda text: message.answer(text, reply_markup=back_to_wallet_keyboard()),
    )


def _topup_payment_keyboard(pay_url: str, amount_usdt: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔓 Оплатить — {amount_usdt} USDT", url=pay_url)],
            [InlineKeyboardButton(text="◀️ К кошельку", callback_data="wallet")],
        ]
    )


async def _create_topup_invoice(
    *,
    telegram_id: int,
    username: str | None,
    amount_kopecks: int,
    session_pool: async_sessionmaker[AsyncSession],
    send: Callable[..., Awaitable[object]],
    on_error: Callable[[str], Awaitable[object]],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=telegram_id, username=username)
        payload = create_topup_payload(user.id, amount_kopecks)
        amount_usdt = usdt_amount_for_kopecks(amount_kopecks, settings.rub_per_usdt)

        try:
            invoice = await create_invoice(
                amount=amount_usdt,
                payload=payload,
                description=f"Пополнение баланса UnLock на {format_rub(amount_kopecks)}",
                asset="USDT",
            )
        except CryptoBotError:
            logger.exception("Failed to create top-up invoice for user_id=%s", user.id)
            await on_error("Не удалось создать счёт. Попробуйте позже.")
            return

        pay_url = invoice.get("pay_url") or invoice.get("bot_invoice_url")
        external_invoice_id = invoice.get("invoice_id")
        if not pay_url or external_invoice_id is None:
            logger.error("CryptoBot returned malformed top-up invoice: %s", invoice)
            await on_error("CryptoBot вернул некорректный счёт. Обратитесь в поддержку.")
            return

        await repo.create_cryptobot_payment(
            user_id=user.id,
            amount=billing_api.crypto_minor_units(amount_usdt),
            external_invoice_id=str(external_invoice_id),
            invoice_payload=payload,
            plan="topup",
        )

    text = (
        "➕ <b>Пополнение баланса</b>\n\n"
        + bq(
            f"💰 Сумма: {format_rub(amount_kopecks)}",
            f"💵 К оплате: {amount_usdt} USDT",
            f"📈 Курс: {settings.RUB_PER_USDT}₽/USDT",
        )
        + "\n\nБаланс зачислится автоматически в течение минуты после оплаты."
    )
    await send(text, reply_markup=_topup_payment_keyboard(str(pay_url), amount_usdt))


@router.callback_query(F.data.startswith("topup:"))
async def topup_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    try:
        amount_kopecks = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректная сумма.", show_alert=True)
        return
    if not MIN_TOPUP_KOPECKS <= amount_kopecks <= MAX_TOPUP_KOPECKS:
        await callback.answer("Сумма вне допустимого диапазона.", show_alert=True)
        return

    async def _send(text: str, *, reply_markup: InlineKeyboardMarkup) -> None:
        if callback.message:
            await callback.message.answer(text, reply_markup=reply_markup)
        else:
            await bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)

    async def _error(text: str) -> None:
        await callback.answer(text, show_alert=True)

    await _create_topup_invoice(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        amount_kopecks=amount_kopecks,
        session_pool=session_pool,
        send=_send,
        on_error=_error,
    )
    await callback.answer()


@router.callback_query(F.data == "promo_enter")
async def promo_enter_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoInput.code)
    text = (
        "🎟 <b>Промокод</b>\n\n"
        "Отправьте промокод одним сообщением — бонус зачислится на баланс."
    )
    await _edit_current_message(callback, text, back_to_wallet_keyboard())
    await callback.answer()


def _promo_error_text(exc: promo.PromoError) -> str:
    if isinstance(exc, promo.PromoNotFoundError):
        return "Такого промокода нет. Проверь написание."
    if isinstance(exc, promo.PromoExpiredError):
        return "Срок действия промокода истёк."
    if isinstance(exc, promo.PromoInactiveError):
        return "Промокод отключён."
    if isinstance(exc, promo.PromoExhaustedError):
        return "Промокод уже исчерпан."
    if isinstance(exc, promo.PromoUserLimitError):
        return "Ты уже использовал этот промокод."
    if isinstance(exc, promo.PromoTypeError):
        return "Этот промокод применяется при оплате, а не к балансу."
    return "Промокод не подошёл."


@router.message(PromoInput.code)
async def promo_code_message_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    code = (message.text or "").strip()
    if not code:
        await message.answer("Отправьте промокод текстом или вернитесь в кошелёк.", reply_markup=back_to_wallet_keyboard())
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        try:
            result = await billing_api.redeem_balance_promo(session, user_id=user.id, code=code)
        except promo.PromoError as exc:
            await message.answer(_promo_error_text(exc), reply_markup=back_to_wallet_keyboard())
            return
        balance = await wallet.get_balance(session, user.id)

    await state.clear()
    await message.answer(
        f"🎉 Промокод применён: +{format_rub(result.credited_kopecks)}\n"
        f"Баланс: <b>{format_rub(balance)}</b>",
        reply_markup=back_to_wallet_keyboard(),
    )


@router.callback_query(F.data == "referral")
async def referral_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        stats = await billing_api.get_referral_overview(session, user.id)

    username = await _bot_username(bot)
    link = build_referral_link(username, stats.ref_code or f"tg{callback.from_user.id}")
    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и получайте <b>{stats.reward_percent}%</b> с каждой их оплаты на баланс.\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>\n\n"
        + bq(
            f"👤 Приглашено: {stats.referrals_count}",
            f"💰 Заработано: {format_rub(stats.total_earned_kopecks)}",
        )
    )
    await _edit_current_message(callback, text, back_to_wallet_keyboard())
    await callback.answer()


def _pay_success_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Подключить устройство", callback_data="connect_device")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


@router.callback_query(F.data.startswith("paybal:"))
async def pay_with_balance_handler(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    parts = callback.data.split(":", 2)
    plan_code = parts[1] if len(parts) > 1 else ""
    raw_region = parts[2] if len(parts) > 2 else None
    try:
        tariff = resolve_tariff(plan_code)
    except ValueError:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return

    region: str | None = None
    region_title: str | None = None
    if tariff.tier == "premium":
        if raw_region is None:
            await callback.answer("Не выбрана локация.", show_alert=True)
            return
        try:
            region_option = resolve_premium_region(raw_region)
        except ValueError:
            await callback.answer("Локация не найдена.", show_alert=True)
            return
        region, region_title = region_option.code, region_option.title
        # Balance checkout only for regions backed by a static panel node;
        # autoscaled regions stay crypto-only until provisioning is live.
        if settings.marzban_inbounds_for_region(region) is None:
            await callback.answer("Эта локация пока оплачивается только криптой.", show_alert=True)
            return

    if not is_panel_configured():
        await callback.answer("Сервис временно недоступен. Попробуйте позже.", show_alert=True)
        return

    price_kopecks = tariff.price_rub * 100
    reference = f"plan:{tariff.code}:{uuid.uuid4().hex}"

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        try:
            await wallet.spend(
                session,
                user.id,
                price_kopecks,
                reference=reference,
                description=f"Оплата тарифа {tariff.title}",
            )
        except wallet.InsufficientBalanceError as exc:
            await callback.answer(
                f"Не хватает {format_rub(exc.required - exc.available)} на балансе.",
                show_alert=True,
            )
            return

        try:
            subscription = await activate_panel_subscription(
                session=session,
                user_id=user.id,
                plan=tariff.code,
                region=region,
            )
        except (PanelGatewayError, Exception):
            logger.exception(
                "Balance checkout failed, refunding user_id=%s reference=%s", user.id, reference
            )
            await wallet.deposit(
                session,
                user.id,
                price_kopecks,
                kind=wallet.KIND_REFUND,
                reference=f"{reference}:refund",
                description=f"Возврат за тариф {tariff.title}",
            )
            await callback.answer(
                "Не удалось активировать подписку — деньги вернулись на баланс.",
                show_alert=True,
            )
            return
        balance = await wallet.get_balance(session, user.id)

    card_lines = [f"💎 Тариф: {tariff.title}"]
    if region_title is not None:
        card_lines.append(f"🌍 Локация: {region_title}")
    card_lines.append(f"💰 Списано: {format_rub(price_kopecks)}")
    card_lines.append(f"💳 Остаток: {format_rub(balance)}")
    text = (
        "✅ <b>Тариф оплачен с баланса</b>\n\n"
        + bq(*card_lines)
        + f"\n\n📅 <b>Подписка активна до:</b> {format_msk(subscription.expires_at)}"
    )
    if callback.message:
        await callback.message.answer(text, reply_markup=_pay_success_keyboard())
    await callback.answer()
