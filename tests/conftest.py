import os
import sys
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("WG_SERVER_PUBLIC_KEY", "TESTSERVERPUBKEY=")
os.environ.setdefault("WG_SERVER_ENDPOINT", "127.0.0.1:51821")
os.environ.setdefault("WG_CLIENT_ADDRESS_POOL", "10.9.0.0/24")
os.environ.setdefault("WG_ALLOWED_IPS", "0.0.0.0/0")

# Force-neutralize live credentials so the suite never talks to real services,
# even when a developer .env with real panel/payment secrets is present
# (env vars take precedence over the .env file in pydantic-settings).
os.environ["PANEL_PROVIDER"] = "remnawave"
os.environ["REMNAWAVE_API_URL"] = ""
os.environ["REMNAWAVE_API_TOKEN"] = ""
os.environ["MARZBAN_API_URL"] = ""
os.environ["MARZBAN_ACCESS_TOKEN"] = ""
os.environ["MARZBAN_USERNAME"] = ""
os.environ["MARZBAN_PASSWORD"] = ""
os.environ["MARZBAN_REGION_INBOUNDS"] = "{}"
os.environ["AWG_NODES"] = "{}"
os.environ["AWG_SSH_KEY"] = ""
os.environ["SUB_GATEWAY_URL"] = ""
os.environ["CRYPTOBOT_TOKEN"] = ""
os.environ["VULTR_API_TOKEN"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database.models import Base


@pytest_asyncio.fixture
async def session_pool():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    pool = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield pool
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_pool):
    async with session_pool() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def db(db_session, session_pool):
    yield db_session, session_pool


@pytest.fixture
def fake_bot():
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.send_document = AsyncMock()
    bot.send_photo = AsyncMock()
    return bot


@pytest.fixture
def telegram_user():
    return SimpleNamespace(id=1001, username="alice")
