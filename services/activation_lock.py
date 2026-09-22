"""Одна выдача подписки на клиента за раз.

Срок новой оплаты считается от конца текущей подписки. Две оплаты одного
клиента, пришедшие одновременно (две вкладки ЮKassa, вебхук и бот, повтор
вебхука), читали один и тот же конец и обе ставили «конец + месяц» — клиент
платил дважды, а получал один период (аудит 22.09.2026, BILL-03).

Блокировка двухслойная: внутри процесса — asyncio.Lock на клиента, между
процессами (бот, API, зеркало) — advisory lock PostgreSQL. Advisory lock
держится на отдельном соединении вне общего пула: выдача несколько раз делает
commit, и соединение сессии между ними уходит обратно в пул, а маленький пул
зеркала (3 соединения) иначе мог бы застрять на ожидающих выдачах.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Первый ключ пары pg_advisory_lock(int, int): «UNLK» — чтобы не пересечься
# с чужими advisory lock в той же базе.
LOCK_NAMESPACE = 0x554E4C4B
# Столько ждём выдачу этого же клиента в другом процессе. Дольше — значит,
# та выдача зависла; тогда выдаём без блокировки: доступ за оплату важнее.
LOCK_WAIT_SECONDS = 90.0
LOCK_POLL_SECONDS = 0.25

_local_locks: dict[int, asyncio.Lock] = {}
_local_users: dict[int, int] = {}
_lock_engines: dict[URL, AsyncEngine] = {}


def _lock_engine(url: URL) -> AsyncEngine:
    engine = _lock_engines.get(url)
    if engine is None:
        engine = create_async_engine(url, poolclass=NullPool)
        _lock_engines[url] = engine
    return engine


@asynccontextmanager
async def _local_lock(user_id: int) -> AsyncIterator[None]:
    lock = _local_locks.setdefault(user_id, asyncio.Lock())
    _local_users[user_id] = _local_users.get(user_id, 0) + 1
    try:
        async with lock:
            yield
    finally:
        _local_users[user_id] -= 1
        if _local_users[user_id] == 0:
            del _local_users[user_id]
            del _local_locks[user_id]


@asynccontextmanager
async def _database_lock(url: URL, user_id: int) -> AsyncIterator[None]:
    connection = await _lock_engine(url).connect()
    locked = False
    try:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            locked = bool(
                await connection.scalar(
                    text("SELECT pg_try_advisory_lock(:ns, :uid)"), {"ns": LOCK_NAMESPACE, "uid": user_id}
                )
            )
            if locked or time.monotonic() >= deadline:
                break
            await asyncio.sleep(LOCK_POLL_SECONDS)
        if not locked:
            logger.error("activation lock for user %s not acquired in %.0fs, activating anyway", user_id, LOCK_WAIT_SECONDS)
        yield
    finally:
        try:
            if locked:
                await connection.scalar(
                    text("SELECT pg_advisory_unlock(:ns, :uid)"), {"ns": LOCK_NAMESPACE, "uid": user_id}
                )
        finally:
            # Закрытие соединения снимает блокировку и тогда, когда unlock не прошёл.
            await connection.close()


@asynccontextmanager
async def user_activation_lock(session: AsyncSession, user_id: int) -> AsyncIterator[None]:
    """Пока открыт блок, другие выдачи этому клиенту ждут."""
    async with _local_lock(user_id):
        bind = session.bind
        if bind is None or bind.dialect.name != "postgresql":
            yield
            return
        async with _database_lock(bind.url, user_id):
            yield
