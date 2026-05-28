import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.keyboards.main_menu import back_to_menu_keyboard
from config import settings
from database.repository import Repository
from services.cryptobot import get_invoices_by_status
from services.payment import parse_invoice_payload
from services.qrcode import generate_qr_png_bytes
from services.subscription import activate_subscription
from services.wireguard import WireGuardError, ensure_user_peer, remove_peer

logger = logging.getLogger(__name__)


async def check_expiring_subscriptions(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        subscriptions = await repo.get_expiring_subscriptions(days=3)
        for subscription in subscriptions:
            try:
                await bot.send_message(
                    chat_id=subscription.user.telegram_id,
                    text=(
                        "Ваша VPN-подписка закончится в течение 3 дней.\n"
                        "Чтобы не потерять доступ, продлите подписку в разделе «Купить VPN»."
                    ),
                )
                await repo.mark_subscription_reminded(subscription.id)
            except Exception:
                logger.exception("Failed to send expiration reminder for subscription_id=%s", subscription.id)


async def deactivate_expired_subscriptions(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    async with session_pool() as session:
        repo = Repository(session)
        subscriptions = await repo.get_expired_active_subscriptions()
        for subscription in subscriptions:
            key = await repo.get_wireguard_key_by_user_id(subscription.user_id)
            if key is not None:
                try:
                    await remove_peer(key.public_key)
                except WireGuardError:
                    logger.exception("Failed to remove WireGuard peer for user_id=%s", subscription.user_id)

            await repo.deactivate_subscription(subscription.id)
            try:
                await bot.send_message(
                    chat_id=subscription.user.telegram_id,
                    text="Ваша VPN-подписка истекла. Доступ отключен.",
                )
            except Exception:
                logger.exception("Failed to notify expired subscription user_id=%s", subscription.user_id)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _access_text(expires_at: datetime) -> str:
    return (
        "✅ Оплата получена!\n"
        f"Подписка активна до {_aware(expires_at):%d.%m.%Y %H:%M} UTC\n\n"
        "🔑 Твой WireGuard-ключ (.conf файл прикреплён ниже)\n"
        "📸 QR-код для импорта — следующим сообщением\n\n"
        "📖 Как подключиться:\n"
        "1. Скачай WireGuard:\n"
        "   • iOS: App Store\n"
        "   • Android: Google Play\n"
        "   • Windows/Mac: wireguard.com/install\n"
        "2. В приложении нажми «+» → «Импорт из файла» или «Сканировать QR»\n"
        "3. Включи туннель — готово\n\n"
        f"Проблемы? {settings.support_contact}"
    )


async def _send_access_bundle(bot: Bot, telegram_id: int, config_text: str, expires_at: datetime) -> None:
    qr_bytes = await generate_qr_png_bytes(config_text)
    await bot.send_message(chat_id=telegram_id, text=_access_text(expires_at))
    await bot.send_document(
        chat_id=telegram_id,
        document=BufferedInputFile(config_text.encode("utf-8"), filename=f"wireguard_{telegram_id}.conf"),
        caption="WireGuard-конфиг для UnLock.",
    )
    await bot.send_photo(
        chat_id=telegram_id,
        photo=BufferedInputFile(qr_bytes, filename="wireguard_qr.png"),
        caption="QR-код для импорта в WireGuard.",
        reply_markup=back_to_menu_keyboard(),
    )


async def poll_cryptobot_payments(
    bot: Bot,
    session_pool: async_sessionmaker[AsyncSession],
) -> None:
    try:
        invoices = await get_invoices_by_status("paid", count=100)
    except Exception:
        logger.exception("CryptoBot polling failed")
        return

    for invoice in invoices:
        external_invoice_id = invoice.get("invoice_id")
        if external_invoice_id is None:
            logger.warning("Skipping paid CryptoBot invoice without invoice_id: %s", invoice)
            continue

        async with session_pool() as session:
            repo = Repository(session)
            payment = await repo.get_payment_by_external_id(str(external_invoice_id))
            if payment is None:
                continue
            if payment.status != "pending":
                continue

            payload = str(invoice.get("payload") or payment.invoice_payload or "")
            try:
                payload_user_id, plan = parse_invoice_payload(payload)
            except ValueError:
                logger.exception(
                    "Invalid CryptoBot invoice payload for external_invoice_id=%s payload=%s",
                    external_invoice_id,
                    payload,
                )
                continue

            if payload_user_id != payment.user_id:
                logger.error(
                    "CryptoBot payment user mismatch external_invoice_id=%s payload_user_id=%s payment_user_id=%s",
                    external_invoice_id,
                    payload_user_id,
                    payment.user_id,
                )
                continue

            completed_payment = await repo.complete_payment_by_external_id(str(external_invoice_id))
            if completed_payment is None:
                continue

            try:
                subscription = await activate_subscription(
                    session=session,
                    user_id=completed_payment.user_id,
                    plan=plan,
                )
                _, config_text = await ensure_user_peer(session=session, user_id=completed_payment.user_id)
                user = await repo.get_user(completed_payment.user_id)
                if user is None:
                    logger.error("Completed payment has no user user_id=%s", completed_payment.user_id)
                    continue
                await _send_access_bundle(
                    bot=bot,
                    telegram_id=user.telegram_id,
                    config_text=config_text,
                    expires_at=subscription.expires_at,
                )
            except Exception:
                logger.exception(
                    "Failed to provision CryptoBot payment external_invoice_id=%s user_id=%s",
                    external_invoice_id,
                    completed_payment.user_id,
                )


def setup_scheduler(bot: Bot, session_pool: async_sessionmaker[AsyncSession]) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(
        check_expiring_subscriptions,
        trigger="interval",
        hours=1,
        args=[bot, session_pool],
        id="check_expiring_subscriptions",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        deactivate_expired_subscriptions,
        trigger="interval",
        hours=1,
        args=[bot, session_pool],
        id="deactivate_expired_subscriptions",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        poll_cryptobot_payments,
        trigger="interval",
        seconds=settings.CRYPTOBOT_POLL_INTERVAL,
        args=[bot, session_pool],
        id="poll_cryptobot_payments",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    return scheduler
