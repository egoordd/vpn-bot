import asyncio
import html
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, ErrorEvent
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.alerts import send_alert

from bot.handlers import admin, buy, connect_device, email_settings, help, instructions, locations, start, subscription, support, wallet
from bot.middlewares.subscription_check import SubscriptionCheckMiddleware
from bot.middlewares.update_timing import SlowUpdateLoggingMiddleware
from config import settings
from database.models import Base
from scheduler.tasks import setup_scheduler
from services.subscription import sync_default_plans
from services.wireguard import resync_all_peers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def init_db(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def main() -> None:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
    )
    session_pool = async_sessionmaker(engine, expire_on_commit=False)

    await init_db(engine)
    async with session_pool() as session:
        await sync_default_plans(session)

    try:
        async with session_pool() as session:
            resynced_count = await resync_all_peers(session)
        logger.info("Re-synced %s WireGuard peers", resynced_count)
    except Exception as exc:
        logger.warning("Failed to re-sync WireGuard peers on startup: %s", exc)

    bot_session = AiohttpSession(proxy=settings.BOT_PROXY) if settings.BOT_PROXY else None
    if bot_session is not None:
        logger.info("Telegram API via proxy: %s", settings.BOT_PROXY)
    bot = Bot(
        token=settings.bot_token,
        session=bot_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage.from_url(settings.REDIS_URL)
    dispatcher = Dispatcher(storage=storage)
    dispatcher["session_pool"] = session_pool

    subscription_middleware = SubscriptionCheckMiddleware()
    timing_middleware = SlowUpdateLoggingMiddleware(settings.SLOW_UPDATE_THRESHOLD_SECONDS)
    dispatcher.message.middleware(timing_middleware)
    dispatcher.callback_query.middleware(timing_middleware)
    dispatcher.message.middleware(subscription_middleware)
    dispatcher.callback_query.middleware(subscription_middleware)

    dispatcher.include_router(start.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(help.router)
    dispatcher.include_router(buy.router)
    dispatcher.include_router(wallet.router)
    dispatcher.include_router(email_settings.router)
    dispatcher.include_router(subscription.router)
    dispatcher.include_router(locations.router)
    dispatcher.include_router(connect_device.router)
    dispatcher.include_router(instructions.router)
    dispatcher.include_router(support.router)

    @dispatcher.errors()
    async def on_update_error(event: ErrorEvent) -> bool:
        exc = event.exception
        logger.exception("Update processing error", exc_info=exc)
        detail = html.escape(f"{type(exc).__name__}: {exc}")[:600]
        await send_alert(
            f"⚠️ <b>Ошибка в боте</b>\n<code>{detail}</code>",
            throttle_key=f"{type(exc).__name__}:{exc}"[:120],
        )
        return True

    scheduler = setup_scheduler(bot=bot, session_pool=session_pool)
    scheduler.start()
    logger.info("Bot started")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главное меню"),
                BotCommand(command="help", description="Помощь и поддержка"),
                BotCommand(command="wallet", description="Кошелёк"),
                BotCommand(command="invite", description="Пригласить друга"),
                BotCommand(command="email", description="Email для чеков"),
            ]
        )
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await storage.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
