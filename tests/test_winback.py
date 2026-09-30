"""Спецпредложение тем, кто взял пробник и так и не подключился (01.10.2026)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError

from bot.handlers import buy
from bot.keyboards.main_menu import tier_plans_keyboard
from database.repository import Repository
from services import billing_api, winback
from services.subscription import activate_panel_subscription
from services.tariffs import TARIFFS
from tests.test_subscription import FakeGenericPanelGateway

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


async def _trial_user(
    session,
    telegram_id: int,
    *,
    trial_ended: timedelta = timedelta(days=2),
    traffic: int = 0,
):
    repo = Repository(session)
    user = await repo.create_user(telegram_id=telegram_id)
    await repo.create_subscription(
        user_id=user.id,
        plan="trial",
        tier="trial",
        panel_username=f"tg_{telegram_id}",
        sub_token=f"t{telegram_id}",
        traffic_used_bytes=traffic,
        started_at=NOW - trial_ended - timedelta(days=3),
        expires_at=NOW - trial_ended,
        is_active=False,
    )
    return user


async def _paid(session, user_id: int, plan: str = "standard_1m", ref: str = "yk") -> None:
    repo = Repository(session)
    await repo.create_yookassa_payment(
        user_id=user_id,
        amount=19900,
        external_invoice_id=f"{ref}-{user_id}",
        invoice_payload=f"unlock:{user_id}:{plan}:{ref}",
        plan=plan,
    )
    await repo.complete_payment_by_external_id(f"{ref}-{user_id}", provider="yookassa")


# --- тарифы ------------------------------------------------------------------


def test_winback_tariffs_are_unlimited_at_the_agreed_prices():
    expected = {"winback_unlim_1m": (30, 179), "winback_unlim_3m": (90, 489), "winback_unlim_6m": (180, 899)}
    for code, (days, price) in expected.items():
        tariff = TARIFFS[code]
        assert (tariff.duration_days, tariff.price_rub) == (days, price)
        assert tariff.traffic_gb is None and tariff.traffic_limit_bytes is None
        assert tariff.device_limit == 3
        assert tariff.tier == "standard"
        assert tariff.hidden is True
    assert winback.WINBACK_PLANS == tuple(expected)


def test_winback_tariffs_stay_out_of_every_public_catalogue():
    keyboard = tier_plans_keyboard("standard")
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert not any("winback" in (data or "") for data in callbacks)
    assert not any(plan.code.startswith("winback") for plan in billing_api.list_billing_plans())


# --- кому отправлять ---------------------------------------------------------


@pytest.mark.integration
async def test_candidates_are_trial_users_who_never_connected_or_paid(db_session):
    fits = await _trial_user(db_session, 70001)
    await _trial_user(db_session, 70002, traffic=5 * 1024**2)  # подключался
    paid = await _trial_user(db_session, 70003)
    await _paid(db_session, paid.id)
    await _trial_user(db_session, -9000000000070004)  # зеркало/сайт — не основной бот
    await _trial_user(db_session, 70005, trial_ended=timedelta(hours=5))  # пробник только кончился
    await _trial_user(db_session, 70006, trial_ended=-timedelta(days=1))  # пробник ещё идёт
    connected = await _trial_user(db_session, 70007)
    await Repository(db_session).record_funnel_event(connected.id, "first_connect")
    offered = await _trial_user(db_session, 70008)
    await winback.grant_offer(db_session, offered.id, now=NOW - timedelta(days=10))

    candidates = await winback.find_candidates(db_session, now=NOW)

    assert [user.telegram_id for user in candidates] == [fits.telegram_id]


# --- предложение -------------------------------------------------------------


@pytest.mark.integration
async def test_offer_lasts_72_hours_and_ends_with_the_purchase(db_session):
    user = await _trial_user(db_session, 70101)
    offer = await winback.grant_offer(db_session, user.id, now=NOW)

    assert offer.expires_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=72)
    assert await winback.active_offer(db_session, user.id, now=NOW + timedelta(hours=71)) is not None
    assert await winback.active_offer(db_session, user.id, now=NOW + timedelta(hours=73)) is None

    await _paid(db_session, user.id, plan="winback_unlim_1m", ref="wb")
    assert await winback.active_offer(db_session, user.id, now=NOW + timedelta(hours=1)) is None


# --- рассылка ----------------------------------------------------------------


@pytest.mark.integration
async def test_nothing_is_sent_while_switched_off(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(winback.settings, "WINBACK_ENABLED", False)
    async with session_pool() as session:
        await _trial_user(session, 70201)
        await session.commit()

    sent = await winback.send_winback_offers(fake_bot, session_pool, now=NOW, pause=0)

    assert sent == 0
    fake_bot.send_message.assert_not_awaited()


@pytest.mark.integration
async def test_each_candidate_gets_the_offer_once(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(winback.settings, "WINBACK_ENABLED", True)
    async with session_pool() as session:
        user = await _trial_user(session, 70301)
        await session.commit()

    assert await winback.send_winback_offers(fake_bot, session_pool, now=NOW, pause=0) == 1
    assert await winback.send_winback_offers(fake_bot, session_pool, now=NOW + timedelta(hours=1), pause=0) == 0

    fake_bot.send_message.assert_awaited_once()
    call = fake_bot.send_message.await_args
    assert call.args[0] == 70301
    text = call.args[1]
    assert "179" in text and "489" in text and "899" in text
    assert "04 октября 2026" in text  # 72 часа от рассылки, по Москве
    callbacks = [b.callback_data for row in call.kwargs["reply_markup"].inline_keyboard for b in row]
    assert [c for c in callbacks if c and c.startswith("buy:")] == [f"buy:{plan}" for plan in winback.WINBACK_PLANS]
    async with session_pool() as session:
        assert await winback.active_offer(session, user.id, now=NOW) is not None


@pytest.mark.integration
async def test_a_user_who_blocked_the_bot_is_not_retried(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(winback.settings, "WINBACK_ENABLED", True)
    fake_bot.send_message = AsyncMock(
        side_effect=TelegramForbiddenError(method=SimpleNamespace(), message="bot was blocked by the user")
    )
    async with session_pool() as session:
        user = await _trial_user(session, 70401)
        await session.commit()

    assert await winback.send_winback_offers(fake_bot, session_pool, now=NOW, pause=0) == 0
    assert await winback.send_winback_offers(fake_bot, session_pool, now=NOW + timedelta(hours=1), pause=0) == 0

    assert fake_bot.send_message.await_count == 1
    async with session_pool() as session:
        assert await winback.active_offer(session, user.id, now=NOW) is None


# --- покупка -----------------------------------------------------------------


def _callback(data: str, telegram_id: int):
    message = SimpleNamespace(photo=None, edit_text=AsyncMock())
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=telegram_id, username=None),
        message=message,
        answer=AsyncMock(),
    )


@pytest.mark.integration
async def test_winback_price_is_closed_without_an_offer(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    create = AsyncMock()
    monkeypatch.setattr(buy.yookassa, "create_payment", create)
    async with session_pool() as session:
        await _trial_user(session, 70501)
        await session.commit()

    checkout = _callback("buy:winback_unlim_1m", 70501)
    await buy.buy_plan_handler(checkout, fake_bot, session_pool)
    pay = _callback("payyk:winback_unlim_1m", 70501)
    await buy.pay_yookassa_handler(pay, fake_bot, session_pool, AsyncMock())

    checkout.message.edit_text.assert_not_awaited()
    assert checkout.answer.await_args.kwargs.get("show_alert") is True
    create.assert_not_awaited()


@pytest.mark.integration
async def test_winback_checkout_opens_for_the_offer_holder(session_pool, fake_bot, monkeypatch):
    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    async with session_pool() as session:
        user = await _trial_user(session, 70601)
        await winback.grant_offer(session, user.id, now=datetime.now(timezone.utc))
        await session.commit()

    checkout = _callback("buy:winback_unlim_1m", 70601)
    await buy.buy_plan_handler(checkout, fake_bot, session_pool)

    text = checkout.message.edit_text.await_args.args[0]
    assert "179₽" in text
    keyboard = checkout.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "payyk:winback_unlim_1m"


@pytest.mark.integration
async def test_a_crafted_target_does_not_follow_the_winback_price(session_pool, fake_bot, monkeypatch):
    """The discount renews the account itself, never a second subscription."""
    monkeypatch.setattr(buy.yookassa, "is_configured", lambda: True)
    async with session_pool() as session:
        user = await _trial_user(session, 70701)
        await winback.grant_offer(session, user.id, now=datetime.now(timezone.utc))
        await session.commit()

    checkout = _callback("buy:winback_unlim_1m@new", 70701)
    await buy.buy_plan_handler(checkout, fake_bot, session_pool)

    keyboard = checkout.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "payyk:winback_unlim_1m"


# --- расписание --------------------------------------------------------------


def test_offers_go_out_once_a_day_at_22_moscow(fake_bot):
    """Решение владельца 01.10.2026: не раз в час, а раз в день в 22:00 по Москве."""
    from scheduler.tasks import setup_scheduler

    job = setup_scheduler(fake_bot, AsyncMock()).get_job("send_winback_offers")

    after_noon = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    after_evening = datetime(2026, 10, 1, 19, 30, tzinfo=timezone.utc)
    assert job.trigger.get_next_fire_time(None, after_noon) == datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)
    assert job.trigger.get_next_fire_time(None, after_evening) == datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)


# --- админ-команда -----------------------------------------------------------


def _admin_message(text: str, telegram_id: int = 4):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=telegram_id, username="admin"),
        answer=AsyncMock(),
    )


@pytest.mark.integration
async def test_winback_report_counts_without_sending(session_pool, fake_bot, monkeypatch):
    from bot.handlers import admin

    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    monkeypatch.setattr(winback.settings, "WINBACK_ENABLED", False)
    async with session_pool() as session:
        await _trial_user(session, 70901, trial_ended=timedelta(days=3))
        await session.commit()
    message = _admin_message("/winback")

    await admin.winback_handler(message, session_pool, fake_bot)

    report = message.answer.await_args_list[0].args[0]
    assert "выключена" in report
    assert "Подходят сейчас: 1" in report
    fake_bot.send_message.assert_not_awaited()


@pytest.mark.integration
async def test_winback_test_opens_the_offer_for_the_admin(session_pool, fake_bot, monkeypatch):
    from bot.handlers import admin

    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    message = _admin_message("/winback test")

    await admin.winback_handler(message, session_pool, fake_bot)

    fake_bot.send_message.assert_awaited_once()
    assert fake_bot.send_message.await_args.args[0] == 4
    async with session_pool() as session:
        assert await winback.purchase_allowed(session, 4, "winback_unlim_1m") is True


@pytest.mark.integration
async def test_winback_command_is_admin_only(session_pool, fake_bot, monkeypatch):
    from bot.handlers import admin

    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    message = _admin_message("/winback test", telegram_id=5)

    await admin.winback_handler(message, session_pool, fake_bot)

    fake_bot.send_message.assert_not_awaited()


# --- выдача ------------------------------------------------------------------


@pytest.mark.integration
async def test_unlimited_really_lifts_the_trial_cap_in_the_panel(db_session):
    """Marzban drops None from a modify call, so «no limit» must travel as 0 —
    otherwise the former trial keeps its 10 GB cap after paying for unlimited."""
    user = await _trial_user(db_session, 70801)
    panel = FakeGenericPanelGateway(exists=True)

    subscription = await activate_panel_subscription(db_session, user.id, "winback_unlim_1m", panel_gateway=panel)

    assert panel.modified[0]["traffic_limit_bytes"] == 0
    assert subscription.traffic_limit_bytes is None
    assert subscription.plan == "winback_unlim_1m"


@pytest.mark.integration
async def test_a_regular_renewal_after_the_offer_brings_the_limit_back(db_session):
    """Безлимит — только на оплаченный по предложению срок. Следующее продление
    обычным тарифом возвращает месячную квоту и в панели, и в базе, а скидка
    второй раз не открывается."""
    user = await _trial_user(db_session, 70901)
    await winback.grant_offer(db_session, user.id)
    panel = FakeGenericPanelGateway(exists=True)
    await activate_panel_subscription(db_session, user.id, "winback_unlim_1m", panel_gateway=panel)

    renewed = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=panel)

    quota = 150 * 1024**3
    assert panel.modified[-1]["traffic_limit_bytes"] == quota
    assert panel.modified[-1]["traffic_resets_monthly"] is True
    assert renewed.traffic_limit_bytes == quota
    assert renewed.plan == "standard_1m"
    active = await Repository(db_session).list_active_subscriptions(user.id)
    assert [s.plan for s in active] == ["standard_1m"], "безлимитная запись погашена"
    assert await winback.purchase_allowed(db_session, 70901, "winback_unlim_1m") is False
