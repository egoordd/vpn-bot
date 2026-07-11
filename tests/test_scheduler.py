from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from scheduler import tasks
from services.panel_client import PanelUsage, PanelUser, RemnawaveNotFoundError
from services.panel_gateway import PanelAccount
from services.payment import create_invoice_payload
from services.wireguard import WireGuardError


@pytest.mark.integration
async def test_poll_cryptobot_payments_crypto_error_returns(fake_bot, session_pool, monkeypatch):
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(side_effect=RuntimeError("down")))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    fake_bot.send_message.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_invoice_without_id(fake_bot, session_pool, monkeypatch):
    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"payload": "x"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_no_matching_payment(fake_bot, session_pool, monkeypatch):
    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"invoice_id": "missing"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_non_pending_payment(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=500)
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-done", "payload", "standard_1m")
        await repo.update_payment_status(payment.id, "completed")

    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"invoice_id": "inv-done"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_invalid_payload(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=501)
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-bad", "bad-payload", "standard_1m")

    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "get_invoices_by_status", AsyncMock(return_value=[{"invoice_id": "inv-bad"}]))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)
        assert refreshed.status == "pending"
    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_skips_payload_user_mismatch(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=502)
        other = await repo.create_user(telegram_id=503)
        payload = create_invoice_payload(other.id, "standard_1m")
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-mismatch", payload, "standard_1m")

    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-mismatch", "payload": payload}]),
    )
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)
        assert refreshed.status == "pending"
    ensure_user_peer.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_happy_path(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=504)
        payload = create_invoice_payload(user.id, "standard_1m")
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-paid", payload, "standard_1m")

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-paid", "payload": payload}]),
    )
    ensure_user_peer = AsyncMock(return_value=(None, "client-config"))
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)
    monkeypatch.setattr(tasks, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        repo = Repository(session)
        refreshed = await repo.get_payment(payment.id)
        subscription = await repo.get_active_subscription(user.id)

    assert refreshed.status == "completed"
    assert subscription is not None
    ensure_user_peer.assert_awaited_once()
    fake_bot.send_message.assert_awaited_once()
    fake_bot.send_document.assert_awaited_once()
    fake_bot.send_photo.assert_awaited_once()


@pytest.mark.integration
async def test_poll_cryptobot_payments_credits_referrer(fake_bot, session_pool, monkeypatch):
    from services import wallet
    from services.referral import attach_referrer

    async with session_pool() as session:
        repo = Repository(session)
        referrer = await repo.create_user(telegram_id=600)
        referee = await repo.create_user(telegram_id=601)
        await attach_referrer(session, user_id=referee.id, ref_code=referrer.ref_code)
        payload = create_invoice_payload(referee.id, "standard_1m")
        await repo.create_cryptobot_payment(referee.id, 199, "inv-ref", payload, "standard_1m")

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-ref", "payload": payload}]),
    )
    monkeypatch.setattr(tasks, "ensure_user_peer", AsyncMock(return_value=(None, "client-config")))
    monkeypatch.setattr(tasks, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        # standard_1m is 149 RUB -> 20% referral reward = 2980 kopecks
        assert await wallet.get_balance(session, referrer.id) == 2980

    # Polling the same paid invoice again must not double-credit the referrer.
    await tasks.poll_cryptobot_payments(fake_bot, session_pool)
    async with session_pool() as session:
        assert await wallet.get_balance(session, referrer.id) == 2980


@pytest.mark.integration
async def test_poll_cryptobot_payments_retries_when_legacy_provisioning_fails(
    fake_bot,
    session_pool,
    monkeypatch,
):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=514)
        payload = create_invoice_payload(user.id, "standard_1m")
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-wg-fails", payload, "standard_1m")

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-wg-fails", "payload": payload}]),
    )
    monkeypatch.setattr(tasks, "_remnawave_configured", lambda: False)
    monkeypatch.setattr(tasks, "ensure_user_peer", AsyncMock(side_effect=WireGuardError("wg down")))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)

    assert refreshed.status == "pending"
    fake_bot.send_message.assert_not_awaited()
    fake_bot.send_document.assert_not_awaited()
    fake_bot.send_photo.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_panel_happy_path(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=505)
        payload = create_invoice_payload(user.id, "standard_1m")
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-panel", payload, "standard_1m")

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-panel", "payload": payload}]),
    )
    monkeypatch.setattr(tasks, "_remnawave_configured", lambda: True)
    activate_panel_subscription = AsyncMock(
        return_value=SimpleNamespace(
            subscription_url="https://sub.example/api/sub/paid",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "activate_panel_subscription", activate_panel_subscription)
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)
    monkeypatch.setattr(tasks, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)

    assert refreshed.status == "completed"
    activate_panel_subscription.assert_awaited_once()
    ensure_user_peer.assert_not_awaited()
    fake_bot.send_message.assert_awaited_once()
    fake_bot.send_photo.assert_awaited_once()
    fake_bot.send_document.assert_not_awaited()


@pytest.mark.integration
async def test_poll_cryptobot_payments_panel_premium_assigns_selected_region(fake_bot, session_pool, monkeypatch):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=516)
        payload = create_invoice_payload(user.id, "premium_1m", region="ams")
        payment = await repo.create_cryptobot_payment(user.id, 499, "inv-premium", payload, "premium_1m")

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-premium", "payload": payload}]),
    )
    monkeypatch.setattr(tasks, "_remnawave_configured", lambda: True)
    activate_panel_subscription = AsyncMock(
        return_value=SimpleNamespace(
            id=700,
            subscription_url="https://sub.example/api/sub/premium",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    assign_subscription_to_node = AsyncMock(return_value=SimpleNamespace(region="ams"))
    monkeypatch.setattr(tasks, "activate_panel_subscription", activate_panel_subscription)
    monkeypatch.setattr(tasks, "assign_subscription_to_node", assign_subscription_to_node)
    monkeypatch.setattr(tasks, "generate_qr_png_bytes", AsyncMock(return_value=b"png"))

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)

    assert refreshed.status == "completed"
    activate_panel_subscription.assert_awaited_once()
    assign_subscription_to_node.assert_awaited_once()
    assign_kwargs = assign_subscription_to_node.await_args.kwargs
    assert assign_kwargs["subscription_id"] == 700
    assert assign_kwargs["region"] == "ams"
    assert assign_kwargs["provision_request"].country_code == "NL"
    assert "Нидерланды, Амстердам" in fake_bot.send_message.await_args.kwargs["text"]


@pytest.mark.integration
async def test_poll_cryptobot_payments_retries_when_panel_provisioning_fails(
    fake_bot,
    session_pool,
    monkeypatch,
):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=515)
        payload = create_invoice_payload(user.id, "standard_1m")
        payment = await repo.create_cryptobot_payment(user.id, 199, "inv-panel-fails", payload, "standard_1m")

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "inv-panel-fails", "payload": payload}]),
    )
    monkeypatch.setattr(tasks, "_remnawave_configured", lambda: True)
    activate_panel_subscription = AsyncMock(side_effect=RuntimeError("panel down"))
    ensure_user_peer = AsyncMock()
    monkeypatch.setattr(tasks, "activate_panel_subscription", activate_panel_subscription)
    monkeypatch.setattr(tasks, "ensure_user_peer", ensure_user_peer)

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_payment(payment.id)

    assert refreshed.status == "pending"
    activate_panel_subscription.assert_awaited_once()
    ensure_user_peer.assert_not_awaited()
    fake_bot.send_message.assert_not_awaited()
    fake_bot.send_photo.assert_not_awaited()


class FakePanelClient:
    def __init__(self, users: dict[str, PanelUser] | None = None, missing: set[str] | None = None):
        self.users = users or {}
        self.missing = missing or set()

    async def get_user(self, username: str) -> PanelUser:
        if username in self.missing:
            raise RemnawaveNotFoundError("missing")
        return self.users[username]


class FakePanelGateway:
    async def get_user(self, username: str) -> PanelAccount:
        return PanelAccount(
            username=username,
            short_uuid=username,
            subscription_url=f"https://marzban.example/sub/{username}",
            status="active",
            expire_at=1783036800,
            traffic_limit_bytes=10 * 1024**3,
            used_traffic_bytes=3 * 1024**3,
            lifetime_used_traffic_bytes=3 * 1024**3,
            device_limit=None,
            provider="marzban",
        )


def _panel_user(
    username: str,
    used: int,
    *,
    limit: int | None = 10 * 1024**3,
    status: str = "ACTIVE",
) -> PanelUser:
    return PanelUser(
        uuid=f"uuid-{username}",
        username=username,
        short_uuid=f"short-{username}",
        subscription_url=f"https://sub.example/api/sub/{username}",
        status=status,
        expire_at="2026-07-03T00:00:00Z",
        traffic_limit_bytes=limit,
        traffic_limit_strategy="NO_RESET",
        hwid_device_limit=3,
        usage=PanelUsage(used_traffic_bytes=used, lifetime_used_traffic_bytes=used),
    )


@pytest.mark.integration
async def test_traffic_sync_updates_panel_subscription_usage(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=506)
        subscription = await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="tg_506",
            sub_token="old",
            subscription_url="https://sub.example/old",
            traffic_limit_bytes=10 * 1024**3,
            traffic_used_bytes=0,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )

    synced = await tasks.traffic_sync(
        fake_bot,
        session_pool,
        panel_client=FakePanelClient({"tg_506": _panel_user("tg_506", used=2 * 1024**3)}),
    )

    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)

    assert synced == 1
    assert refreshed.is_active is True
    assert refreshed.status == "active"
    assert refreshed.traffic_used_bytes == 2 * 1024**3
    assert refreshed.device_limit == 3
    assert refreshed.sub_token == "short-tg_506"
    assert refreshed.subscription_url == "https://sub.example/api/sub/tg_506"
    fake_bot.send_message.assert_not_awaited()


@pytest.mark.integration
async def test_traffic_sync_accepts_generic_panel_gateway(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=509)
        subscription = await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="mz_509",
            traffic_limit_bytes=10 * 1024**3,
            traffic_used_bytes=0,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )

    synced = await tasks.traffic_sync(fake_bot, session_pool, panel_gateway=FakePanelGateway())

    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)

    assert synced == 1
    assert refreshed.is_active is True
    assert refreshed.status == "active"
    assert refreshed.traffic_used_bytes == 3 * 1024**3
    assert refreshed.device_limit is None
    assert refreshed.sub_token == "mz_509"
    assert refreshed.subscription_url == "https://marzban.example/sub/mz_509"
    fake_bot.send_message.assert_not_awaited()


@pytest.mark.integration
async def test_traffic_sync_deactivates_when_traffic_limit_is_reached(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=507)
        subscription = await repo.create_subscription(
            user_id=user.id,
            plan="trial",
            tier="trial",
            panel_username="tg_507",
            traffic_limit_bytes=10 * 1024**3,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_active=True,
        )

    await tasks.traffic_sync(
        fake_bot,
        session_pool,
        panel_client=FakePanelClient({"tg_507": _panel_user("tg_507", used=10 * 1024**3)}),
    )

    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)

    assert refreshed.is_active is False
    assert refreshed.status == "limited"
    fake_bot.send_message.assert_awaited_once()


@pytest.mark.integration
async def test_traffic_sync_deactivates_missing_panel_user(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=508)
        subscription = await repo.create_subscription(
            user_id=user.id,
            plan="trial",
            tier="trial",
            panel_username="tg_508",
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            is_active=True,
        )

    synced = await tasks.traffic_sync(fake_bot, session_pool, panel_client=FakePanelClient(missing={"tg_508"}))

    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)

    assert synced == 1
    assert refreshed.is_active is False
    assert refreshed.status == "not_found"
    fake_bot.send_message.assert_awaited_once()


@pytest.mark.integration
async def test_check_expiring_subscriptions_sends_and_marks(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=600)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=2),
            True,
        )

    await tasks.check_expiring_subscriptions(fake_bot, session_pool)

    fake_bot.send_message.assert_awaited_once()
    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.last_reminded_at is not None


@pytest.mark.integration
async def test_check_expiring_subscriptions_catches_send_errors(session_pool):
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=601)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(days=2),
            True,
        )

    await tasks.check_expiring_subscriptions(bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.last_reminded_at is None


@pytest.mark.integration
async def test_deactivate_expired_subscriptions_removes_peer_and_notifies(fake_bot, session_pool, monkeypatch):
    remove_peer = AsyncMock()
    monkeypatch.setattr(tasks, "remove_peer", remove_peer)
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=700)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc) - timedelta(days=31),
            datetime.now(timezone.utc) - timedelta(days=1),
            True,
        )
        await repo.create_wireguard_key(user.id, "PUB", "PRIV", "10.9.0.2", "/client.conf")

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    remove_peer.assert_awaited_once_with("PUB")
    fake_bot.send_photo.assert_awaited_once()
    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.is_active is False


@pytest.mark.integration
async def test_deactivate_expired_subscriptions_catches_remove_peer_errors(fake_bot, session_pool, monkeypatch):
    remove_peer = AsyncMock(side_effect=WireGuardError("cannot remove"))
    monkeypatch.setattr(tasks, "remove_peer", remove_peer)
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=701)
        subscription = await repo.create_subscription(
            user.id,
            "1m",
            datetime.now(timezone.utc) - timedelta(days=31),
            datetime.now(timezone.utc) - timedelta(days=1),
            True,
        )
        await repo.create_wireguard_key(user.id, "PUBERR", "PRIV", "10.9.0.2", "/client.conf")

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    remove_peer.assert_awaited_once_with("PUBERR")
    fake_bot.send_photo.assert_awaited_once()
    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
        assert refreshed.is_active is False


@pytest.mark.integration
async def test_deactivate_expired_subscriptions_releases_premium_nodes(fake_bot, session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=702)
        node = await repo.create_node(
            tier="premium",
            capacity=2,
            region="ams",
            provider="manual",
            ip_address="203.0.113.70",
            panel_node_id="panel-premium",
            current_users=1,
        )
        subscription = await repo.create_subscription(
            user_id=user.id,
            plan="premium_1m",
            tier="premium",
            node_ids=["panel-premium"],
            started_at=datetime.now(timezone.utc) - timedelta(days=31),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            is_active=True,
        )

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    async with session_pool() as session:
        repo = Repository(session)
        refreshed_node = await repo.get_node(node.id)
        refreshed_subscription = await repo.get_subscription(subscription.id)

    assert refreshed_node.current_users == 0
    assert refreshed_subscription.node_ids == []
    assert refreshed_subscription.is_active is False
    fake_bot.send_photo.assert_awaited_once()


@pytest.mark.integration
async def test_autoscale_check_noops_without_configured_regions(session_pool, monkeypatch):
    autoscale_premium_pool = AsyncMock()
    monkeypatch.setattr(tasks, "AUTOSCALE_PREMIUM_REGIONS", "", raising=False)
    monkeypatch.setattr(tasks.settings, "AUTOSCALE_PREMIUM_REGIONS", "")
    monkeypatch.setattr(tasks, "autoscale_premium_pool", autoscale_premium_pool)

    result = await tasks.autoscale_check(session_pool)

    assert result.checked_regions == 0
    assert result.provisioned_count == 0
    autoscale_premium_pool.assert_not_awaited()


@pytest.mark.integration
async def test_autoscale_check_delegates_with_explicit_regions(session_pool, monkeypatch):
    expected = tasks.AutoscalePoolResult(checked_regions=1, provisioned_node_ids=[10])
    autoscale_premium_pool = AsyncMock(return_value=expected)
    monkeypatch.setattr(tasks, "autoscale_premium_pool", autoscale_premium_pool)

    result = await tasks.autoscale_check(
        session_pool,
        regions=["ams"],
        min_free_slots=2,
        min_active_nodes=1,
        max_provisions_per_region=1,
        decommission_empty=False,
    )

    assert result is expected
    autoscale_premium_pool.assert_awaited_once()
    kwargs = autoscale_premium_pool.await_args.kwargs
    assert kwargs["regions"] == ["ams"]
    assert kwargs["min_free_slots"] == 2
    assert kwargs["min_active_nodes"] == 1
    assert kwargs["max_provisions_per_region"] == 1
    assert kwargs["decommission_empty"] is False


@pytest.mark.unit
def test_access_text_and_aware_helpers():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = tasks._aware(naive)

    assert aware.tzinfo == timezone.utc
    assert "01.01.2026 12:00 UTC" in tasks._access_text(naive)


@pytest.mark.integration
async def test_poll_cryptobot_payments_credits_topup(fake_bot, session_pool, monkeypatch):
    from services import wallet as wallet_service
    from services.payment import create_topup_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=880, username="topupper")
        payload = create_topup_payload(user.id, 15000)
        await repo.create_cryptobot_payment(
            user_id=user.id,
            amount=167,
            external_invoice_id="top-ext-1",
            invoice_payload=payload,
            plan="topup",
        )

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "top-ext-1", "payload": payload}]),
    )

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        repo = Repository(session)
        balance = await repo.get_balance(user.id)
        payment = await repo.get_payment_by_external_id("top-ext-1")
    assert balance == 15000
    assert payment.status == "completed"
    fake_bot.send_message.assert_awaited_once()
    text = fake_bot.send_message.await_args.kwargs["text"]
    assert "150₽" in text


@pytest.mark.integration
async def test_poll_cryptobot_payments_topup_is_idempotent(fake_bot, session_pool, monkeypatch):
    from services.payment import create_topup_payload

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=881, username="topupper2")
        payload = create_topup_payload(user.id, 30000)
        await repo.create_cryptobot_payment(
            user_id=user.id,
            amount=334,
            external_invoice_id="top-ext-2",
            invoice_payload=payload,
            plan="topup",
        )

    monkeypatch.setattr(
        tasks,
        "get_invoices_by_status",
        AsyncMock(return_value=[{"invoice_id": "top-ext-2", "payload": payload}]),
    )

    await tasks.poll_cryptobot_payments(fake_bot, session_pool)
    await tasks.poll_cryptobot_payments(fake_bot, session_pool)

    async with session_pool() as session:
        balance = await Repository(session).get_balance(user.id)
    assert balance == 30000


# --- deactivate_expired_subscriptions: panel enforcement ---------------------

class RecordingPanelGateway:
    def __init__(self):
        self.modified: list[dict] = []

    async def modify_user(self, **kwargs):
        self.modified.append(kwargs)


async def _make_panel_subscription(session_pool, telegram_id: int, panel_username: str, *, expires_in: timedelta, is_active: bool = True):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_or_create_user(telegram_id=telegram_id) if hasattr(repo, "get_or_create_user") else await repo.create_user(telegram_id=telegram_id)
        now = datetime.now(timezone.utc)
        subscription = await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username=panel_username,
            sub_token=f"tok-{panel_username}-{now.timestamp()}",
            subscription_url=f"https://sub.example/{panel_username}",
            started_at=now - timedelta(days=30),
            expires_at=now + expires_in,
            is_active=is_active,
        )
    return user, subscription


@pytest.mark.integration
async def test_deactivate_expired_disables_panel_user(fake_bot, session_pool, monkeypatch):
    _, subscription = await _make_panel_subscription(
        session_pool, 601, "tg_601", expires_in=timedelta(hours=-1)
    )
    panel = RecordingPanelGateway()
    monkeypatch.setattr(tasks, "is_panel_configured", lambda: True)
    monkeypatch.setattr(tasks, "get_panel_gateway", lambda: panel)

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    assert len(panel.modified) == 1
    assert panel.modified[0]["username"] == "tg_601"
    assert panel.modified[0]["status"] == "disabled"
    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
    assert refreshed.is_active is False


@pytest.mark.integration
async def test_deactivate_expired_keeps_panel_user_of_renewed_line(fake_bot, session_pool, monkeypatch):
    # Same panel user: one expired row plus a paid renewal that is still live.
    user, _ = await _make_panel_subscription(
        session_pool, 602, "tg_602", expires_in=timedelta(hours=-1)
    )
    async with session_pool() as session:
        repo = Repository(session)
        now = datetime.now(timezone.utc)
        await repo.create_subscription(
            user_id=user.id,
            plan="standard_1m",
            tier="standard",
            panel_username="tg_602",
            sub_token="tok-renewal-602",
            subscription_url="https://sub.example/tg_602",
            started_at=now,
            expires_at=now + timedelta(days=30),
            is_active=True,
        )
    panel = RecordingPanelGateway()
    monkeypatch.setattr(tasks, "is_panel_configured", lambda: True)
    monkeypatch.setattr(tasks, "get_panel_gateway", lambda: panel)

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    assert panel.modified == []


@pytest.mark.integration
async def test_deactivate_expired_survives_panel_error(fake_bot, session_pool, monkeypatch):
    from services.panel_gateway import PanelGatewayError

    _, subscription = await _make_panel_subscription(
        session_pool, 603, "tg_603", expires_in=timedelta(hours=-1)
    )

    class FailingPanelGateway:
        async def modify_user(self, **kwargs):
            raise PanelGatewayError("panel down")

    monkeypatch.setattr(tasks, "is_panel_configured", lambda: True)
    monkeypatch.setattr(tasks, "get_panel_gateway", lambda: FailingPanelGateway())

    await tasks.deactivate_expired_subscriptions(fake_bot, session_pool)

    async with session_pool() as session:
        refreshed = await Repository(session).get_subscription(subscription.id)
    assert refreshed.is_active is False
