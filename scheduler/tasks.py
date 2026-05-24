import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.repository import Repository
from services.wireguard import WireGuardError, remove_peer

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
    return scheduler
