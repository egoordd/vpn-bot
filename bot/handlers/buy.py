import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers.start import _menu_state
from bot.keyboards.main_menu import (
    renew_durations_keyboard,
    renew_menu_keyboard,
    tier_plans_keyboard,
)
from bot.navigation import show_screen
from bot.texts import bq
from config import settings
from database.repository import Repository
from services.billing_api import build_payment_intent, register_yookassa_payment
from services.payment import PLANS, normalize_payment_plan_code
from services.tariffs import resolve_tariff
from services import subscription_slots as slots
from services import winback
from services import yookassa

logger = logging.getLogger(__name__)
router = Router()

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




def _back_for_target(target: str | None, tier: str) -> str:
    """Один шаг назад: к выбору срока той же покупки."""
    if target == slots.TARGET_NEW:
        return "buy_extra"
    if target is not None:
        return f"renew_sub:{target}"
    return f"buy_tier:{tier}"


def _checkout_keyboard(
    *,
    plan: str,
    yookassa_ok: bool = False,
    tier: str = "standard",
    target: str | None = None,
) -> InlineKeyboardMarkup:
    suffix = ""
    rows: list[list[InlineKeyboardButton]] = []
    if yookassa_ok:
        # Card is the primary method → first button. Creates a YooKassa payment on
        # tap, then shows its confirmation URL.
        rows.append(
            [
                InlineKeyboardButton(
                    text="💳 Оплатить картой",
                    callback_data=f"payyk:{slots.with_target(plan, target)}{suffix}",
                )
            ]
        )
    # One step back = this tier's plan list, not the tier-select screen.
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=_back_for_target(target, tier))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _target_line(target: str | None) -> str | None:
    if target == slots.TARGET_NEW:
        return "➕ Ещё одна подписка: отдельная ссылка и свои устройства"
    if target is not None:
        return "🔄 Продление выбранной подписки"
    return None


def build_checkout_view(plan: str, target: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура экрана оплаты одного тарифа.

    Отдельно от хэндлера, потому что на этот экран ведут два пути: кнопка в
    боте и deep-link `/start buy_<план>` из рекламы и кабинета. Раньше второго
    пути не было, и ссылка на конкретный тариф высаживала человека в главное меню.
    """
    tariff = resolve_tariff(plan)
    yookassa_ok = yookassa.is_configured() and tariff.tier == "standard"

    card_lines = [
        f"💎 Тариф: {tariff.title}",
        f"💵 Стоимость: {tariff.price_rub}₽",
    ]
    target_line = _target_line(target)
    if target_line:
        card_lines.insert(0, target_line)
    sections = ["💳 <b>Оплата тарифа</b>\n\n" + bq(*card_lines)]
    if yookassa_ok:
        sections.append(
            "Нажмите «Оплатить картой» — откроется защищённая страница оплаты. "
            "После оплаты подписка придёт сюда автоматически."
        )
    else:
        sections.append("⚠️ Оплата временно недоступна. Попробуйте позже.")

    return "\n\n".join(sections), _checkout_keyboard(
        plan=plan, yookassa_ok=yookassa_ok, tier=tariff.tier, target=target
    )


async def _show_checkout(
    callback: CallbackQuery,
    session_pool: async_sessionmaker[AsyncSession],
    *,
    plan: str,
    target: str | None = None,
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )

    text, keyboard = build_checkout_view(plan, target)
    await _edit_current_message(callback, text, keyboard)
    await callback.answer()


def _yookassa_pay_keyboard(
    pay_url: str,
    price_rub: int,
    *,
    plan: str | None = None,
    email_editable: bool = False,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"💳 Оплатить — {price_rub}₽", url=pay_url)]]
    if email_editable and plan:
        # The чек goes to the stored email; a typo would send it nowhere, so
        # let the buyer fix the address right from the payment screen.
        suffix = ""
        rows.append(
            [InlineKeyboardButton(text="✏️ Изменить email для чека", callback_data=f"ykemail:{plan}{suffix}")]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class YookassaEmailInput(StatesGroup):
    email = State()


def _email_prompt_keyboard(plan: str) -> InlineKeyboardMarkup:
    # Cancel = one step back to this plan's checkout, not the buy menu.
    back = f"buy:{plan}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data=back)]])


async def _create_yookassa_invoice(
    *,
    telegram_id: int,
    username: str | None,
    session_pool: async_sessionmaker[AsyncSession],
    plan: str,
    email: str | None,
    send,
    target: str | None = None,
) -> None:
    if not await _winback_allowed(session_pool, telegram_id, plan):
        await send(WINBACK_CLOSED, None)
        return
    async with session_pool() as session:
        intent = await build_payment_intent(
            session,
            telegram_id=telegram_id,
            username=username,
            plan=plan,
            target=target,
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
    invoice_lines = [f"💎 Тариф: {intent.plan.title}", f"💵 Стоимость: {intent.plan.price_rub}₽"]
    target_line = _target_line(target)
    if target_line:
        invoice_lines.insert(0, target_line)
    text = (
        "💳 <b>Оплата картой</b>\n\n"
        + bq(*invoice_lines)
        + "\n\nНажмите кнопку ниже и оплатите на защищённой странице.\n"
        + receipt_line
        + "Ссылка-подписка придёт автоматически в течение минуты после оплаты."
    )
    await send(
        text,
        _yookassa_pay_keyboard(
            pay_url,
            intent.plan.price_rub,
            plan=slots.with_target(plan, target),
            email_editable=bool(email),
        ),
    )



TIER_TEXTS = {
    "standard": (
        "🚀 <b>Обычный тариф</b>\n\n"
        "<blockquote>"
        "⚡️ Авто-обход — сам переключается на рабочий сервер\n"
        "🌍 Локации: 🇱🇹 Литва, 🇵🇱 Польша, 🇩🇪 Германия, 🇳🇱 Нидерланды, 🇺🇸 США\n"
        "🇷🇺 Вход через Москву — банки и госуслуги продолжают работать\n"
        "🔀 Переключение между серверами прямо в приложении\n"
        "📊 150–200 ГБ трафика в месяц — зависит от срока\n"
        "📱 До 3 устройств, на 6 и 12 месяцев — до 5"
        "</blockquote>\n\n"
        "Выберите срок:"
    ),
}


EXTRA_TEXT = (
    "➕ <b>Ещё одна подписка</b>\n\n"
    "<blockquote>"
    "🔗 Отдельная ссылка — например, для семьи\n"
    "📱 Ещё до 3 устройств, на 6 и 12 месяцев — до 5\n"
    "📊 Свой трафик: 150–200 ГБ в месяц — зависит от срока\n"
    "⏳ Срок идёт с момента оплаты, основная подписка не меняется"
    "</blockquote>\n\n"
    "Выберите срок:"
)


def _parse_plan(raw: str) -> tuple[str, str | None]:
    """«standard_1m@new» → (код тарифа, цель). ValueError — если что-то не так."""
    raw_plan, target = slots.split_plan_target(raw)
    plan = normalize_payment_plan_code(raw_plan)
    if winback.is_winback_plan(plan):
        # Скидка продлевает сам аккаунт, а не отдельную подписку.
        target = None
    return plan, target


WINBACK_CLOSED = "Это предложение уже недоступно: срок истёк или скидка уже использована."


async def _winback_allowed(session_pool: async_sessionmaker[AsyncSession], telegram_id: int, plan: str) -> bool:
    """Скидочный тариф открыт только держателю действующего предложения."""
    if not winback.is_winback_plan(plan):
        return True
    async with session_pool() as session:
        return await winback.purchase_allowed(session, telegram_id, plan)


async def _extra_allowed(session_pool: async_sessionmaker[AsyncSession], telegram_id: int, username: str | None) -> bool:
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=telegram_id, username=username)
        return slots.can_add(await repo.list_active_subscriptions(user.id))


LIMIT_ALERT = f"На одном аккаунте может быть не больше {slots.MAX_SUBSCRIPTIONS} подписок."


@router.callback_query(F.data == "buy_extra")
async def buy_extra_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    if not await _extra_allowed(session_pool, callback.from_user.id, callback.from_user.username):
        await callback.answer(LIMIT_ALERT, show_alert=True)
        return
    await _edit_current_message(callback, EXTRA_TEXT, tier_plans_keyboard("standard", target=slots.TARGET_NEW))
    await callback.answer()


@router.callback_query(F.data == "buy_menu")
async def buy_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    # Single tier for now — skip the tier picker and go straight to durations.
    await state.clear()  # drop any pending email-input state
    await _edit_current_message(callback, TIER_TEXTS["standard"], tier_plans_keyboard("standard"))
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
            "🔄 <b>Продление</b>\n\nУ вас нет активных подписок. Оформите тариф через «🛒 Купить подписку».",
            tier_plans_keyboard("standard"),
        )
        await callback.answer()
        return

    # One subscription means the picker offers exactly one button, which asks
    # the user nothing — go straight to the durations. It used to be worth a
    # screen when Premium and Standard could both be active at once.
    if len(subscriptions) == 1:
        await _edit_current_message(
            callback,
            "🔄 <b>Продление</b>\n\nВыберите срок — он добавится к текущему:",
            renew_durations_keyboard(
                subscriptions[0].tier, back_callback="main_menu", target=str(subscriptions[0].id)
            ),
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
        tier = subscription.tier

    # Reached from the picker, so «Назад» belongs there.
    text = "🔄 <b>Продление</b>\n\nВыберите срок — он добавится к текущему:"
    await _edit_current_message(
        callback, text, renew_durations_keyboard(tier, back_callback="renew_menu", target=str(sub_id))
    )
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
        plan, target = _parse_plan(raw_plan)
    except ValueError:
        await callback.answer("Тариф не найден", show_alert=True)
        return
    if target == slots.TARGET_NEW and not await _extra_allowed(
        session_pool, callback.from_user.id, callback.from_user.username
    ):
        await callback.answer(LIMIT_ALERT, show_alert=True)
        return
    if not await _winback_allowed(session_pool, callback.from_user.id, plan):
        await callback.answer(WINBACK_CLOSED, show_alert=True)
        return

    await _show_checkout(callback, session_pool, plan=plan, target=target)



@router.callback_query(F.data.startswith("payyk:"))
async def pay_yookassa_handler(
    callback: CallbackQuery,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
    state: FSMContext,
) -> None:
    parts = callback.data.split(":", maxsplit=2) if callback.data else []
    raw_plan = parts[1] if len(parts) >= 2 else ""
    try:
        plan, target = _parse_plan(raw_plan)
    except ValueError:
        await callback.answer("Тариф не найден", show_alert=True)
        return
    if target == slots.TARGET_NEW and not await _extra_allowed(
        session_pool, callback.from_user.id, callback.from_user.username
    ):
        await callback.answer(LIMIT_ALERT, show_alert=True)
        return

    if not yookassa.is_configured():
        await callback.answer("Оплата картой сейчас недоступна.", show_alert=True)
        return
    if not await _winback_allowed(session_pool, callback.from_user.id, plan):
        await callback.answer(WINBACK_CLOSED, show_alert=True)
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
        await state.update_data(plan=plan, **({"target": target} if target else {}))
        text = (
            "📧 <b>Email для чека</b>\n\n"
            + bq(
                "По закону (54-ФЗ) на оплату картой формируется чек.",
                "Он придёт вам на email.",
            )
            + "\n\nОтправьте ваш email одним сообщением (например, <code>name@mail.ru</code>)."
        )
        await _send_callback_message(callback, bot, text, _email_prompt_keyboard(slots.with_target(plan, target)))
        return

    await _create_yookassa_invoice(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        session_pool=session_pool,
        plan=plan,
        email=stored_email,
        send=lambda text, kb: _send_callback_message(callback, bot, text, kb),
        target=target,
    )


@router.callback_query(F.data.startswith("ykemail:"))
async def yookassa_change_email_handler(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":", maxsplit=2) if callback.data else []
    raw_plan = parts[1] if len(parts) >= 2 else ""
    try:
        plan, target = _parse_plan(raw_plan)
    except ValueError:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    await state.set_state(YookassaEmailInput.email)
    await state.update_data(plan=plan, **({"target": target} if target else {}))
    text = (
        "✏️ <b>Новый email для чека</b>\n\n"
        "Отправьте адрес одним сообщением (например, <code>name@mail.ru</code>) — "
        "мы сохраним его и выставим счёт заново."
    )
    await _send_callback_message(callback, bot, text, _email_prompt_keyboard(slots.with_target(plan, target)))
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
            reply_markup=_email_prompt_keyboard(
                slots.with_target(str(data.get("plan") or ""), data.get("target"))
            ),
        )
        return

    data = await state.get_data()
    await state.clear()
    plan = data.get("plan")
    target = data.get("target")
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
        email=email,
        send=lambda text, kb: message.answer(text, reply_markup=kb),
        target=target,
    )
