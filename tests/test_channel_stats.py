"""/channels: одна база, три входа — бот, сайт и зеркало.

/stats показывает проект целиком; здесь те же цифры разложены по тому, откуда
пришёл аккаунт. Сумма трёх колонок обязана сходиться с /stats, иначе разбивке
нельзя верить.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services import channel_stats, mirror_bot


def test_mirror_boundary_matches_the_mirror():
    assert channel_stats.MIRROR_CEILING == mirror_bot.mirror_account_id(0)


async def _seed(session) -> None:
    repo = Repository(session)
    now = datetime.now(timezone.utc)
    live = {"started_at": now, "expires_at": now + timedelta(days=30)}

    bot_trial = await repo.create_user(telegram_id=6001)
    await repo.create_subscription(user_id=bot_trial.id, plan="trial", **live)
    bot_buyer = await repo.create_user(telegram_id=6002)
    await repo.create_subscription(user_id=bot_buyer.id, plan="standard_1m", **live)
    await repo.create_payment(user_id=bot_buyer.id, amount=14900, currency="RUB", status="completed")
    await repo.create_payment(user_id=bot_buyer.id, amount=250, currency="USDT", status="completed")
    await repo.create_payment(user_id=bot_buyer.id, amount=14900, currency="RUB", status="pending")

    site_buyer = await repo.create_user(telegram_id=-123_456_789)
    await repo.create_subscription(user_id=site_buyer.id, plan="standard_3m", **live)
    await repo.create_payment(user_id=site_buyer.id, amount=39900, currency="RUB", status="completed")
    await repo.create_user(telegram_id=-123_456_790)

    mirror_buyer = await repo.create_user(telegram_id=mirror_bot.mirror_account_id(7001))
    await repo.create_subscription(user_id=mirror_buyer.id, plan="standard_1m", **live)
    await repo.create_subscription(
        user_id=mirror_buyer.id,
        plan="trial",
        started_at=now - timedelta(days=9),
        expires_at=now - timedelta(days=2),
        is_active=False,
    )
    await repo.create_payment(user_id=mirror_buyer.id, amount=19900, currency="RUB", status="completed")
    await session.commit()


@pytest.mark.integration
async def test_collect_splits_accounts_by_where_they_came_from(db_session):
    await _seed(db_session)

    stats = await channel_stats.collect(db_session)

    assert stats["bot"] == channel_stats.ChannelStats(
        users_total=2, users_day=2, users_week=2,
        trials_active=1, paid_active=1,
        payments_total=2, payments_week=2,
        revenue_total_rub=149, revenue_week_rub=149,
    )
    assert stats["site"] == channel_stats.ChannelStats(
        users_total=2, users_day=2, users_week=2,
        trials_active=0, paid_active=1,
        payments_total=1, payments_week=1,
        revenue_total_rub=399, revenue_week_rub=399,
    )
    assert stats["mirror"] == channel_stats.ChannelStats(
        users_total=1, users_day=1, users_week=1,
        trials_active=0, paid_active=1,
        payments_total=1, payments_week=1,
        revenue_total_rub=199, revenue_week_rub=199,
    )


@pytest.mark.integration
async def test_render_shows_each_channel_and_totals_that_match_stats(db_session):
    await _seed(db_session)
    repo = Repository(db_session)

    text = channel_stats.render(await channel_stats.collect(db_session))

    for title in ("🤖 <b>Бот</b>", "🌐 <b>Сайт</b>", "🪞 <b>Зеркало</b>", "Σ <b>Всего</b>"):
        assert title in text
    assert "Пользователей: 2 (+2 за 24ч, +2 за 7д)" in text
    assert "Активных подписок: 1 (платных 1, пробных 0)" in text
    assert "Оплат: 1 на 399 ₽ (за 7д: 1 на 399 ₽)" in text
    active = sum((await repo.count_active_subscriptions_by_tier()).values())
    assert f"Пользователей: {await repo.count_users()} (" in text
    assert f"Активных подписок: {active} (платных 3, пробных 1)" in text
    assert "Оплат: 4 на 747 ₽" in text
    assert "через Telegram" in text


@pytest.mark.integration
async def test_channels_handler_is_admin_only(session_pool, monkeypatch):
    from bot.handlers import admin

    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "777")
    async with session_pool() as session:
        await _seed(session)

    stranger = SimpleNamespace(from_user=SimpleNamespace(id=5555, username="x"), answer=AsyncMock())
    await admin.channels_handler(stranger, session_pool)
    assert "Бот" not in stranger.answer.await_args.args[0]

    owner = SimpleNamespace(from_user=SimpleNamespace(id=777, username="adm"), answer=AsyncMock())
    await admin.channels_handler(owner, session_pool)
    text = owner.answer.await_args.args[0]
    assert "🌐 <b>Сайт</b>" in text
    assert "Оплат: 1 на 399 ₽" in text
