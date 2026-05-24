import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from bot.keyboards.tariffs import tariffs_keyboard
from database.repository import Repository
from services.payment import PLANS, create_invoice_payload, parse_invoice_payload, send_invoice
from services.qrcode import generate_qr_png_bytes
from services.subscription import activate_subscription
from services.wireguard import WireGuardError, ensure_user_peer

logger = logging.getLogger(__name__)
router = Router()


class BuyStates(StatesGroup):
    choosing_plan = State()
    waiting_payment = State()


@router.callback_query(F.data == "buy_vpn")
async def show_tariffs(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BuyStates.choosing_plan)
    text = "Выберите тариф. Оплата проходит через Telegram Stars."
    if callback.message:
        await callback.message.edit_text(text, reply_markup=tariffs_keyboard())
    await callback.answer()


@router.callback_query(BuyStates.choosing_plan, F.data.startswith("buy:"))
async def buy_tariff(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    plan = callback.data.split(":", maxsplit=1)[1]
    if plan not in PLANS:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        payload = create_invoice_payload(user_id=user.id, plan=plan)
        await repo.create_payment(
            user_id=user.id,
            amount=int(PLANS[plan]["amount"]),
            currency="XTR",
            invoice_payload=payload,
            status="pending",
        )

    await send_invoice(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=user.id,
        plan=plan,
        payload=payload,
    )
    await state.set_state(BuyStates.waiting_payment)
    await state.update_data(plan=plan, payload=payload)
    if callback.message:
        await callback.message.answer("Счет отправлен. После оплаты бот пришлет конфиг и QR-код.")
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    try:
        _, plan = parse_invoice_payload(pre_checkout_query.invoice_payload)
    except ValueError:
        await pre_checkout_query.answer(ok=False, error_message="Некорректный счет. Создайте новый счет.")
        return

    plan_data = PLANS[plan]
    if pre_checkout_query.currency != "XTR" or pre_checkout_query.total_amount != int(plan_data["amount"]):
        await pre_checkout_query.answer(ok=False, error_message="Сумма платежа не совпадает с тарифом.")
        return

    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(
    message: Message,
    state: FSMContext,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    successful_payment = message.successful_payment
    try:
        payload_user_id, plan = parse_invoice_payload(successful_payment.invoice_payload)
    except ValueError:
        logger.exception("Invalid successful payment payload: %s", successful_payment.invoice_payload)
        await message.answer("Оплата получена, но счет не распознан. Напишите в поддержку.")
        return

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        if user.id != payload_user_id:
            logger.warning("Payment payload user mismatch: payload=%s actual=%s", payload_user_id, user.id)

        payment = await repo.complete_payment_by_payload(
            invoice_payload=successful_payment.invoice_payload,
            telegram_payment_charge_id=successful_payment.telegram_payment_charge_id,
            provider_payment_charge_id=successful_payment.provider_payment_charge_id,
        )
        if payment is None:
            await repo.create_payment(
                user_id=user.id,
                amount=successful_payment.total_amount,
                currency=successful_payment.currency,
                invoice_payload=successful_payment.invoice_payload,
                telegram_payment_charge_id=successful_payment.telegram_payment_charge_id,
                provider_payment_charge_id=successful_payment.provider_payment_charge_id,
                status="completed",
            )

        subscription = await activate_subscription(session=session, user_id=user.id, plan=plan)

        try:
            _, config_text = await ensure_user_peer(session=session, user_id=user.id)
        except WireGuardError:
            logger.exception("WireGuard provisioning failed for user_id=%s", user.id)
            await message.answer(
                "Оплата прошла, подписка активирована, но ключ не удалось подготовить автоматически. "
                "Напишите в поддержку, мы выдадим конфиг вручную.",
                reply_markup=back_to_menu_keyboard(),
            )
            return

    qr_bytes = await generate_qr_png_bytes(config_text)
    filename = f"wireguard_{message.from_user.id}.conf"
    await message.answer(
        f"Оплата прошла. Подписка активна до {subscription.expires_at:%d.%m.%Y %H:%M} UTC."
    )
    await message.answer_document(
        BufferedInputFile(config_text.encode("utf-8"), filename=filename),
        caption="Ваш WireGuard-конфиг.",
    )
    await message.answer_photo(
        BufferedInputFile(qr_bytes, filename="wireguard_qr.png"),
        caption="QR-код для импорта в WireGuard.",
        reply_markup=back_to_menu_keyboard(),
    )
    await state.clear()
