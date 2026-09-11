"""The mirror keeps accounts of its own.

Someone who uses both bots from one Telegram account gets two independent
accounts: what they start or buy in the mirror never shows up in the main bot,
and the main bot's subscription never shows up in the mirror.
"""

from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services import mirror_bot, mirror_platega
from tests.test_mirror_platega import FakeActivation, FakePlatega, FakeTelegram


def _callbacks(markup: dict) -> list[str]:
    return [b["callback_data"] for row in markup["inline_keyboard"] for b in row if "callback_data" in b]


async def _main_bot_subscriber(session, telegram_id: int):
    repo = Repository(session)
    user = await repo.create_user(telegram_id=telegram_id)
    now = datetime.now(timezone.utc)
    await repo.create_subscription(
        user_id=user.id,
        plan="standard_1m",
        started_at=now,
        expires_at=now + timedelta(days=30),
        panel_username=f"tg_{telegram_id}",
        subscription_url="https://example.invalid/sub/main",
    )
    return user


def test_a_mirror_account_collides_with_neither_telegram_nor_website_ids():
    for telegram_id in (1, 740484324, 8_968_470_305, 2**40):
        account = mirror_bot.mirror_account_id(telegram_id)
        assert account < -(2**52) - 1, "website accounts live above -2**52"
        assert mirror_bot.chat_id_of(account) == telegram_id


def test_rows_from_before_the_split_still_reach_their_chat():
    assert mirror_bot.chat_id_of(740484324) == 740484324


@pytest.mark.asyncio
async def test_a_main_bot_subscription_is_not_shown_in_the_mirror(session_pool):
    async with session_pool() as session:
        await _main_bot_subscriber(session, 6001)
    bot = mirror_bot.MirrorBot(FakeTelegram(), session_pool)

    text, keyboard = await bot.menu_state(6001, "both", None)

    assert "Добро пожаловать" in text
    assert "activate_trial" in _callbacks(keyboard)


@pytest.mark.asyncio
async def test_a_trial_taken_in_the_mirror_stays_in_the_mirror(session_pool, monkeypatch):
    async with session_pool() as session:
        main_user = await _main_bot_subscriber(session, 6002)
    monkeypatch.setattr(mirror_bot, "activate_panel_subscription", FakeActivation())
    bot = mirror_bot.MirrorBot(FakeTelegram(), session_pool)

    await bot.handle_callback(
        {
            "id": "cb",
            "from": {"id": 6002, "username": "both"},
            "message": {"chat": {"id": 6002}, "message_id": 1},
            "data": "activate_trial",
        }
    )

    async with session_pool() as session:
        repo = Repository(session)
        mirror_user = await repo.get_user_by_telegram_id(mirror_bot.mirror_account_id(6002))
        main_plans = [s.plan for s in await repo.list_active_subscriptions(main_user.id)]
        mirror_plans = [s.plan for s in await repo.list_active_subscriptions(mirror_user.id)]
    assert main_plans == ["standard_1m"]
    assert mirror_plans == ["trial"]


@pytest.mark.asyncio
async def test_platega_still_learns_the_buyers_real_telegram_id(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_platega, "MERCHANT_ID", "merchant-uuid")
    monkeypatch.setattr(mirror_platega, "SECRET", "secret-key")
    monkeypatch.setattr(mirror_platega, "ENABLED_METHODS", ())
    bot = mirror_bot.MirrorBot(FakeTelegram(), session_pool)
    bot.platega = FakePlatega()

    await bot.handle_callback(
        {
            "id": "cb",
            "from": {"id": 6003, "username": "buyer"},
            "message": {"chat": {"id": 6003}, "message_id": 1},
            "data": "pl_plan:standard_1m",
        }
    )

    assert bot.platega.created[0]["user_id"] == 6003
    async with session_pool() as session:
        repo = Repository(session)
        assert await repo.get_user_by_telegram_id(6003) is None
        assert await repo.get_user_by_telegram_id(mirror_bot.mirror_account_id(6003)) is not None


@pytest.mark.asyncio
async def test_a_paid_invoice_is_announced_in_the_buyers_own_chat(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_platega, "MERCHANT_ID", "merchant-uuid")
    monkeypatch.setattr(mirror_platega, "SECRET", "secret-key")
    real_settle = mirror_platega.settle

    async def settle(session, client, payment_id):
        return await real_settle(session, client, payment_id, activate=FakeActivation())

    monkeypatch.setattr(mirror_platega, "settle", settle)
    alerts: list[str] = []

    async def record_alert(text, **_kwargs):
        alerts.append(text)
        return True

    monkeypatch.setattr(mirror_bot, "send_alert", record_alert)
    telegram = FakeTelegram()
    bot = mirror_bot.MirrorBot(telegram, session_pool)
    bot.platega = FakePlatega(status="CONFIRMED", amount=149.0)
    async with session_pool() as session:
        account = await Repository(session).get_or_create_user(mirror_bot.mirror_account_id(6004), "buyer")
        payment, _ = await mirror_platega.start_payment(
            session, bot.platega, user=account, plan="standard_1m", method=0, payer_id=6004
        )

    assert await bot.settle_and_notify(payment.id) == "completed"
    chats = {payload["chat_id"] for method, payload in telegram.calls if method == "sendMessage"}
    assert chats == {6004}
    assert len(alerts) == 1 and "Оплата в зеркале" in alerts[0]
