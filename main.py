import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers import buy, instructions, key, start, subscription, support
from bot.middlewares.subscription_check import SubscriptionCheckMiddleware
from config import settings
from database.models import Base
from scheduler.tasks import setup_scheduler


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

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage.from_url(settings.REDIS_URL)
    dispatcher = Dispatcher(storage=storage)
    dispatcher["session_pool"] = session_pool

    subscription_middleware = SubscriptionCheckMiddleware()
    dispatcher.message.middleware(subscription_middleware)
    dispatcher.callback_query.middleware(subscription_middleware)

    dispatcher.include_router(start.router)
    dispatcher.include_router(buy.router)
    dispatcher.include_router(subscription.router)
    dispatcher.include_router(key.router)
    dispatcher.include_router(instructions.router)
    dispatcher.include_router(support.router)

    scheduler = setup_scheduler(bot=bot, session_pool=session_pool)
    scheduler.start()
    logger.info("Bot started")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await storage.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
