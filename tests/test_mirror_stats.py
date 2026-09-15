"""/stats в зеркале: только для админов и только про аккаунты зеркала.

Зеркало и основной бот пишут в одну базу. Если сводка зеркала зацепит чужие
строки, по ней уже нельзя будет понять, работает ли зеркало само по себе.
"""

from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services import mirror_bot, mirror_stats
from tests.test_mirror_platega import FakeTelegram

ADMIN = 740484324
STRANGER = 5555
CEILING = mirror_bot.mirror_account_id(0)


def _texts(telegram: FakeTelegram) -> list[str]:
    return [p.get("text", "") for m, p in telegram.calls if m in {"sendMessage", "editMessageText"}]


def _message(telegram_id: int, text: str) -> dict:
    return {"from": {"id": telegram_id, "username": "u"}, "chat": {"id": telegram_id}, "text": text}


async def _seed(session) -> None:
    repo = Repository(session)
    now = datetime.now(timezone.utc)

    # Чужие для зеркала: аккаунт основного бота и покупатель с сайта.
    main = await repo.create_user(telegram_id=6001)
    await repo.create_subscription(
        user_id=main.id, plan="standard_1m", started_at=now, expires_at=now + timedelta(days=30)
    )
    await repo.create_payment(user_id=main.id, amount=14900, currency="RUB", status="completed")
    await repo.record_funnel_event(main.id, "start")
    site = await repo.create_user(telegram_id=-123_456_789)
    await repo.create_payment(user_id=site.id, amount=119900, currency="RUB", status="completed")

    # Зеркало: один на пробном периоде, один купил после пробного.
    trial = await repo.create_user(telegram_id=mirror_bot.mirror_account_id(7001))
    await repo.create_subscription(
        user_id=trial.id, plan="trial", started_at=now, expires_at=now + timedelta(days=7)
    )
    for event in ("start", "trial"):
        await repo.record_funnel_event(trial.id, event)

    buyer = await repo.create_user(telegram_id=mirror_bot.mirror_account_id(7002))
    await repo.create_subscription(
        user_id=buyer.id,
        plan="trial",
        started_at=now - timedelta(days=9),
        expires_at=now - timedelta(days=2),
        is_active=False,
    )
    await repo.create_subscription(
        user_id=buyer.id, plan="standard_3m", started_at=now, expires_at=now + timedelta(days=90)
    )
    await repo.create_payment(user_id=buyer.id, amount=39900, currency="RUB", status="completed")
    await repo.create_payment(user_id=buyer.id, amount=14900, currency="RUB", status="pending")
    for event in ("start", "trial", "first_connect", "payment"):
        await repo.record_funnel_event(buyer.id, event)


@pytest.mark.asyncio
async def test_the_numbers_cover_the_mirror_and_nothing_else(session_pool):
    async with session_pool() as session:
        await _seed(session)
        stats = await mirror_stats.collect(session, account_ceiling=CEILING)

    assert stats.users_total == 2, "аккаунт основного бота и покупатель с сайта — не зеркало"
    assert (stats.trials_total, stats.trials_active) == (2, 1)
    assert stats.paid_by_plan == {"standard_3m": 1}
    assert (stats.payments_total, stats.revenue_total_rub) == (1, 399)
    assert stats.invoices_open == 1, "неоплаченный счёт — не выручка"
    assert stats.funnel == {"start": 2, "trial": 2, "first_connect": 1, "payment": 1}


@pytest.mark.asyncio
async def test_the_admin_gets_the_mirror_summary(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_bot.settings, "ADMIN_IDS", str(ADMIN))
    async with session_pool() as session:
        await _seed(session)
    telegram = FakeTelegram()
    bot = mirror_bot.MirrorBot(telegram, session_pool)

    await bot.handle_message(_message(ADMIN, "/stats"))

    text = _texts(telegram)[-1]
    assert "Статистика зеркала" in text
    assert "Всего: 1 на 399 ₽" in text
    assert "1 199" not in text, "покупка с сайта не должна попасть в выручку зеркала"


@pytest.mark.asyncio
async def test_someone_else_gets_the_menu_and_no_hint_the_command_exists(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_bot.settings, "ADMIN_IDS", str(ADMIN))
    telegram = FakeTelegram()
    bot = mirror_bot.MirrorBot(telegram, session_pool)

    await bot.handle_message(_message(STRANGER, "/stats"))

    texts = _texts(telegram)
    assert texts, "человек должен увидеть обычное меню"
    assert not any("Статистика" in t for t in texts)


def test_an_empty_mirror_still_reads_cleanly():
    text = mirror_stats.render(mirror_stats.MirrorStats())

    assert "Всего: 0 на 0 ₽" in text
    assert "Оплатили: 0" in text, "нулевая воронка не должна падать на делении"
