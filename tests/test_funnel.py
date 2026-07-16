from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.handlers import start
from bot.handlers.admin import _funnel_report
from database.repository import Repository
from scheduler import tasks
from services.panel_client import PanelUsage, PanelUser, RemnawaveNotFoundError
from services.subscription import activate_panel_subscription


def _panel_user(username: str, used: int, *, limit: int | None = 10 * 1024**3) -> PanelUser:
    return PanelUser(
        uuid=f"uuid-{username}",
        username=username,
        short_uuid=f"short-{username}",
        subscription_url=f"https://sub.example/api/sub/{username}",
        status="ACTIVE",
        expire_at="2026-08-01T00:00:00Z",
        traffic_limit_bytes=limit,
        traffic_limit_strategy="NO_RESET",
        hwid_device_limit=3,
        usage=PanelUsage(used_traffic_bytes=used, lifetime_used_traffic_bytes=used),
    )


class FakeSyncPanelClient:
    def __init__(self, users: dict[str, PanelUser]):
        self.users = users

    async def get_user(self, username: str) -> PanelUser:
        return self.users[username]


class FakeProvisionPanelClient:
    async def get_user(self, username: str) -> PanelUser:
        raise RemnawaveNotFoundError("missing")

    async def create_user(self, **kwargs) -> PanelUser:
        return _panel_user(str(kwargs["username"]), used=0)


@pytest.mark.integration
async def test_record_funnel_event_is_once_per_user(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=1001)
        first = await repo.record_funnel_event(user.id, "start")
        repeat = await repo.record_funnel_event(user.id, "start")
        other = await repo.record_funnel_event(user.id, "trial", meta={"plan": "trial"})

    assert first is not None
    assert repeat is None
    assert other is not None
    assert other.meta == {"plan": "trial"}


@pytest.mark.integration
async def test_funnel_counts_respects_since_filter(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        first_user = await repo.create_user(telegram_id=1002)
        second_user = await repo.create_user(telegram_id=1003)
        await repo.record_funnel_event(first_user.id, "start")
        await repo.record_funnel_event(second_user.id, "start")
        await repo.record_funnel_event(first_user.id, "payment")

        counts = await repo.funnel_counts()
        future_only = await repo.funnel_counts(since=datetime.now(timezone.utc) + timedelta(minutes=5))

    assert counts == {"start": 2, "payment": 1}
    assert future_only == {}


@pytest.mark.integration
async def test_complete_payment_by_payload_records_payment_event(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=1004)
        await repo.create_payment(user_id=user.id, amount=14900, invoice_payload="funnel-pl-1")
        await repo.complete_payment_by_payload("funnel-pl-1", telegram_payment_charge_id="tg-charge")
        counts = await repo.funnel_counts()

    assert counts.get("payment") == 1


@pytest.mark.integration
async def test_complete_payment_by_external_id_records_payment_event(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=1005)
        await repo.create_cryptobot_payment(
            user_id=user.id,
            amount=14900,
            external_invoice_id="funnel-inv-9",
            invoice_payload="funnel-pl-9",
            plan="standard_1m",
        )
        payment = await repo.complete_payment_by_external_id("funnel-inv-9")
        counts = await repo.funnel_counts()

    assert payment is not None
    assert counts.get("payment") == 1


@pytest.mark.integration
async def test_start_handler_records_start_event_once(session_pool, fake_bot):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1006, username="funnel_user"),
        chat=SimpleNamespace(id=1006),
        bot=fake_bot,
    )

    await start.start_handler(message, session_pool)
    await start.start_handler(message, session_pool)

    async with session_pool() as session:
        counts = await Repository(session).funnel_counts()
    assert counts.get("start") == 1


@pytest.mark.integration
async def test_trial_activation_records_trial_event(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=1007)
        await activate_panel_subscription(
            session=session,
            user_id=user.id,
            plan="trial",
            panel_client=FakeProvisionPanelClient(),
        )
        counts = await repo.funnel_counts()

    assert counts.get("trial") == 1


@pytest.mark.integration
async def test_paid_plan_activation_does_not_record_trial_event(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=1009)
        await activate_panel_subscription(
            session=session,
            user_id=user.id,
            plan="standard_1m",
            panel_client=FakeProvisionPanelClient(),
        )
        counts = await repo.funnel_counts()

    assert "trial" not in counts


@pytest.mark.integration
async def test_traffic_sync_records_first_connect_once(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=1008)
        await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="tg_1008",
            traffic_limit_bytes=10 * 1024**3,
            traffic_used_bytes=0,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )

    client = FakeSyncPanelClient({"tg_1008": _panel_user("tg_1008", used=1024)})
    await tasks.traffic_sync(fake_bot, session_pool, panel_client=client)
    await tasks.traffic_sync(fake_bot, session_pool, panel_client=client)

    async with session_pool() as session:
        counts = await Repository(session).funnel_counts()
    assert counts.get("first_connect") == 1


@pytest.mark.integration
async def test_traffic_sync_without_usage_records_no_first_connect(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=1010)
        await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="tg_1010",
            traffic_limit_bytes=10 * 1024**3,
            traffic_used_bytes=0,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )

    client = FakeSyncPanelClient({"tg_1010": _panel_user("tg_1010", used=0)})
    await tasks.traffic_sync(fake_bot, session_pool, panel_client=client)

    async with session_pool() as session:
        counts = await Repository(session).funnel_counts()
    assert "first_connect" not in counts


@pytest.mark.unit
def test_funnel_report_formats_conversion_percentages():
    text = _funnel_report(
        {"start": 10, "trial": 5, "first_connect": 2, "payment": 1},
        "За всё время",
    )

    assert "Запустили бота: 10" in text
    assert "Получили триал: 5 (50% от пред.)" in text
    assert "Подключились: 2 (40% от пред.)" in text
    assert "Оплатили: 1 (50% от пред.)" in text


@pytest.mark.integration
async def test_source_captured_first_touch_and_grouped(session_pool):
    # New user arrives via a seeded-channel deep link.
    msg = SimpleNamespace(
        text="/start src_tgchan",
        from_user=SimpleNamespace(id=6001, username="seed", full_name="Seed"),
    )
    await start._record_start_event(session_pool, msg)

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_telegram_id(6001)
        assert user.source == "tgchan"

        # A later /start with a different source must NOT overwrite first-touch.
        await repo.set_user_source_if_unset(user.id, "ads")
        assert (await repo.get_user_by_telegram_id(6001)).source == "tgchan"

        grouped = await repo.source_funnel_counts()
        assert grouped["tgchan"]["start"] == 1


@pytest.mark.integration
async def test_source_funnel_counts_buckets_unknown(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=6002, username="nosrc")
        await repo.record_funnel_event(user.id, "start")

        grouped = await repo.source_funnel_counts()
        assert grouped["(без источника)"]["start"] >= 1


@pytest.mark.unit
def test_source_report_sorts_by_starts():
    from bot.handlers.admin import _source_report

    text = _source_report({
        "small": {"start": 2, "payment": 0},
        "big": {"start": 10, "trial": 4, "payment": 1},
    })
    # bigger source listed first
    assert text.index("big") < text.index("small")
    assert "10 старт → 4 триал → 1 оплат" in text
