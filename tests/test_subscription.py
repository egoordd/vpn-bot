from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services.panel_gateway import PanelAccount, PanelGatewayError, PanelUserNotFoundError
from services.subscription import (
    _aware,
    _device_limit,
    _renewal_starts_at,
    activate_panel_subscription,
    check_subscription_active,
    get_subscription_info,
    to_gateway_subscription_url,
    to_happ_import_url,
)


def test_gateway_url_rewrites_token_to_gateway(monkeypatch):
    monkeypatch.setattr(
        "services.subscription.settings.SUB_GATEWAY_URL",
        "https://144.172.101.217.sslip.io:8444",
    )
    result = to_gateway_subscription_url("https://144.172.101.217.sslip.io:8443/sub/abc123")
    assert result == "https://144.172.101.217.sslip.io:8444/sub/abc123"


def test_gateway_url_passthrough_when_unset(monkeypatch):
    monkeypatch.setattr("services.subscription.settings.SUB_GATEWAY_URL", "")
    raw = "https://144.172.101.217.sslip.io:8443/sub/abc123"
    assert to_gateway_subscription_url(raw) == raw


def test_gateway_url_handles_none_and_non_sub_links(monkeypatch):
    monkeypatch.setattr(
        "services.subscription.settings.SUB_GATEWAY_URL",
        "https://gw.example:8444",
    )
    assert to_gateway_subscription_url(None) is None
    assert to_gateway_subscription_url("https://panel/no-token") == "https://panel/no-token"


def test_happ_import_url_maps_sub_to_happ_path():
    assert (
        to_happ_import_url("https://sub.unlockvpn.org:8444/sub/abc123")
        == "https://sub.unlockvpn.org:8444/happ/abc123"
    )


def test_happ_import_url_none_for_invalid_links():
    assert to_happ_import_url(None) is None
    assert to_happ_import_url("https://panel/no-token") is None


def test_the_tariff_decides_how_many_devices_a_subscription_gets():
    """Колонка в базе пуста у трёх четвертей подписок — цифру знает тариф.

    Пока её брали из колонки, оплативший человек видел «∞ устройств», а выдача
    считала, что ограничивать его не нужно.
    """
    paid = SimpleNamespace(plan="standard_1m", device_limit=None)
    trial = SimpleNamespace(plan="trial", device_limit=1)

    assert _device_limit(paid) == 3
    assert _device_limit(trial) == 2, "старая цифра из базы не должна пережить смену тарифа"


def test_a_plan_we_no_longer_sell_keeps_the_stored_number():
    legacy = SimpleNamespace(plan="promo_2024", device_limit=5)

    assert _device_limit(legacy) == 5


def test_a_forgotten_plan_without_a_stored_number_stays_unlimited():
    assert _device_limit(SimpleNamespace(plan="promo_2024", device_limit=None)) is None


@pytest.mark.integration
async def test_check_subscription_active(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=3)

    assert await check_subscription_active(db_session, user.id) is False

    expired = datetime.now(timezone.utc) - timedelta(days=1)
    await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=expired - timedelta(days=30),
        expires_at=expired,
        is_active=True,
    )
    assert await check_subscription_active(db_session, user.id) is False

    await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )
    assert await check_subscription_active(db_session, user.id) is True


@pytest.mark.integration
async def test_get_subscription_info_states(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=4)

    assert await get_subscription_info(db_session, user.id) == {
        "exists": False,
        "is_active": False,
        "plan": None,
        "plan_title": None,
        "started_at": None,
        "expires_at": None,
    }

    active = await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True,
    )
    info = await get_subscription_info(db_session, user.id)
    assert info["exists"] is True
    assert info["is_active"] is True
    assert info["plan_title"] == "Standard 1 месяц"
    assert info["expires_at"] == active.expires_at

    expired_user = await repo.create_user(telegram_id=5)
    expired = await repo.create_subscription(
        user_id=expired_user.id,
        plan="3m",
        started_at=datetime.now(timezone.utc) - timedelta(days=91),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        is_active=True,
    )
    info = await get_subscription_info(db_session, expired_user.id)
    assert info["exists"] is True
    assert info["is_active"] is False
    assert info["plan_title"] == "Standard 3 месяца"
    assert info["expires_at"] == expired.expires_at


@pytest.mark.unit
def test_aware_converts_naive_and_preserves_aware():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    assert _aware(naive).tzinfo == timezone.utc
    assert _aware(aware) is aware


class FakeGenericPanelGateway:
    provider = "marzban"

    def __init__(self, exists: bool = False, reset_fails: bool = False):
        self.exists = exists
        self.reset_fails = reset_fails
        self.created: list[dict[str, object]] = []
        self.modified: list[dict[str, object]] = []
        self.reset_calls: list[str] = []

    def build_username(self, telegram_id: int) -> str:
        return f"mz_{telegram_id}"

    async def get_user(self, username: str) -> PanelAccount:
        if not self.exists:
            raise PanelUserNotFoundError("missing")
        return self._account(username)

    async def create_user(self, **kwargs) -> PanelAccount:
        self.created.append(kwargs)
        self.exists = True
        return self._account(str(kwargs["username"]))

    async def modify_user(self, **kwargs) -> PanelAccount:
        self.modified.append(kwargs)
        self.exists = True
        return self._account(str(kwargs["username"]))

    async def reset_traffic(self, username: str) -> PanelAccount:
        if self.reset_fails:
            raise PanelGatewayError("panel refused the reset")
        self.reset_calls.append(username)
        return self._account(username, used_traffic_bytes=0)

    def _account(self, username: str, used_traffic_bytes: int = 77) -> PanelAccount:
        return PanelAccount(
            username=username,
            short_uuid=username,
            subscription_url=f"https://marzban.example/sub/{username}",
            status="active",
            expire_at=1783036800,
            traffic_limit_bytes=10 * 1024**3,
            used_traffic_bytes=used_traffic_bytes,
            lifetime_used_traffic_bytes=88,
            provider=self.provider,
        )


@pytest.mark.integration
async def test_activate_panel_subscription_extends_existing_panel_user(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=601)
    now = datetime.now(timezone.utc)
    old = await repo.create_subscription(
        user_id=user.id,
        plan="trial",
        tier="trial",
        panel_username="tg_601",
        sub_token="old",
        started_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=3),
        is_active=True,
    )
    panel = FakeGenericPanelGateway(exists=True)

    subscription = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=panel)
    await db_session.refresh(old)

    assert panel.created == []
    assert panel.modified[0]["username"] == "tg_601"
    assert panel.modified[0]["status"] == "active"
    assert _aware(subscription.started_at) == _aware(old.expires_at)
    assert subscription.plan == "standard_1m"
    assert subscription.tier == "standard"
    assert old.is_active is False


@pytest.mark.integration
async def test_activate_panel_subscription_accepts_generic_panel_gateway(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=602, username="marz")
    gateway = FakeGenericPanelGateway(exists=False)

    subscription = await activate_panel_subscription(db_session, user.id, "trial", panel_gateway=gateway)

    assert gateway.created[0]["username"] == "mz_602"
    assert gateway.created[0]["telegram_id"] == 602
    assert subscription.plan == "trial"
    assert subscription.tier == "trial"
    assert subscription.panel_username == "mz_602"
    assert subscription.sub_token == "mz_602"
    assert subscription.subscription_url == "https://marzban.example/sub/mz_602"
    assert subscription.traffic_used_bytes == 77




def test_connect_page_url_uses_fragment(monkeypatch):
    from services import subscription as sub_mod

    monkeypatch.setattr(sub_mod.settings, "WEB_BASE_URL", "https://unlockvpn.site")
    url = sub_mod.connect_page_url("https://sub.unlockvpn.site/sub/abc123")
    assert url == "https://unlockvpn.site/connect#sub=https%3A%2F%2Fsub.unlockvpn.site%2Fsub%2Fabc123"


def test_connect_page_url_none_when_unset(monkeypatch):
    from services import subscription as sub_mod

    monkeypatch.setattr(sub_mod.settings, "WEB_BASE_URL", "")
    assert sub_mod.connect_page_url("https://x/sub/t") is None
    monkeypatch.setattr(sub_mod.settings, "WEB_BASE_URL", "https://unlockvpn.site")
    assert sub_mod.connect_page_url(None) is None


def test_to_happ_import_url_auto_flavor():
    assert (
        to_happ_import_url("https://sub.unlockvpn.site/sub/abc123", auto=True)
        == "https://sub.unlockvpn.site/happ/abc123/auto"
    )
    # default stays the plain flavor
    assert (
        to_happ_import_url("https://sub.unlockvpn.site/sub/abc123")
        == "https://sub.unlockvpn.site/happ/abc123"
    )


@pytest.mark.unit
async def test_renewal_zeroes_the_carried_over_traffic_counter(db_session):
    """Paying again must buy a fresh allowance, not the remains of the last one.

    The panel counts traffic against the account rather than the period paid
    for, so without this a customer who burned 140 of 150 GB and then renewed
    would get 10 GB for their money.
    """
    user = await Repository(db_session).create_user(telegram_id=6001)
    gateway = FakeGenericPanelGateway(exists=True)

    subscription = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=gateway)

    assert gateway.reset_calls == ["mz_6001"]
    assert subscription.traffic_used_bytes == 0
    assert gateway.modified[0]["traffic_resets_monthly"] is True


@pytest.mark.unit
async def test_first_purchase_creates_the_account_without_a_reset(db_session):
    """A brand-new panel account has nothing to zero."""
    user = await Repository(db_session).create_user(telegram_id=6002)
    gateway = FakeGenericPanelGateway(exists=False)

    await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=gateway)

    assert gateway.reset_calls == []
    assert gateway.created[0]["traffic_resets_monthly"] is True


@pytest.mark.unit
async def test_trial_never_resets_an_existing_counter(db_session):
    """Otherwise re-taking the trial would hand out free traffic on demand."""
    user = await Repository(db_session).create_user(telegram_id=6003)
    gateway = FakeGenericPanelGateway(exists=True)

    await activate_panel_subscription(db_session, user.id, "trial", panel_gateway=gateway)

    assert gateway.reset_calls == []
    assert gateway.modified[0]["traffic_resets_monthly"] is False


@pytest.mark.unit
async def test_a_failed_reset_still_delivers_the_paid_subscription(db_session):
    """Losing the purchase is worse than carrying a stale counter for a while.

    The panel's own 30-day sweep clears the counter either way; a crash here
    would take the activation down with it.
    """
    user = await Repository(db_session).create_user(telegram_id=6004)
    gateway = FakeGenericPanelGateway(exists=True, reset_fails=True)

    subscription = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=gateway)

    assert subscription.is_active is True
    assert subscription.panel_username == "mz_6004"
    assert gateway.reset_calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "tier,status,is_active,expiry_days,paid_renewal,preserve",
    [
        ("standard", "limited", False, 40, True, True),
        ("standard", "LIMITED", False, 40, True, True),
        ("standard", "limited", False, -1, True, False),
        ("standard", "limited", False, 0, True, False),
        ("standard", "disabled", False, 40, True, False),
        ("standard", "revoked", False, 40, True, False),
        ("standard", "active", True, 40, True, True),
        ("trial", "active", True, 2, True, True),
        ("trial", "limited", False, 2, True, False),
        ("standard", "limited", False, 40, False, False),
    ],
)
async def test_renewal_basis_preserves_only_current_entitlement(
    tier, status, is_active, expiry_days, paid_renewal, preserve
):
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    latest = SimpleNamespace(
        id=10,
        user_id=100,
        tier=tier,
        status=status,
        is_active=is_active,
        expires_at=now + timedelta(days=expiry_days),
    )
    repo = SimpleNamespace(list_subscriptions_by_user=AsyncMock(return_value=[latest]))

    result = await _renewal_starts_at(repo, latest, now, paid_renewal=paid_renewal)

    assert result == (latest.expires_at if preserve else now)
    if not is_active and expiry_days > 0 and tier == "standard" and status.lower() == "limited" and paid_renewal:
        repo.list_subscriptions_by_user.assert_awaited_once_with(100)
    else:
        repo.list_subscriptions_by_user.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize("newer_tier,preserve", [("standard", False), ("trial", False), ("premium", True)])
async def test_renewal_basis_does_not_restore_a_superseded_limited_row(newer_tier, preserve):
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    latest = SimpleNamespace(
        id=10,
        user_id=100,
        tier="standard",
        status="limited",
        is_active=False,
        expires_at=now + timedelta(days=100),
    )
    newer = SimpleNamespace(id=11, tier=newer_tier)
    repo = SimpleNamespace(list_subscriptions_by_user=AsyncMock(return_value=[newer, latest]))

    result = await _renewal_starts_at(repo, latest, now, paid_renewal=True)

    assert result == (latest.expires_at if preserve else now)


@pytest.mark.unit
async def test_renewal_basis_handles_missing_subscription_and_naive_expiry():
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    repo = SimpleNamespace(list_subscriptions_by_user=AsyncMock(return_value=[]))
    assert await _renewal_starts_at(repo, None, now, paid_renewal=True) == now

    latest = SimpleNamespace(
        id=10,
        user_id=100,
        tier="standard",
        status="limited",
        is_active=False,
        expires_at=datetime(2026, 10, 9),
    )
    repo.list_subscriptions_by_user.return_value = [latest]
    assert await _renewal_starts_at(repo, latest, now, paid_renewal=True) == datetime(
        2026, 10, 9, tzinfo=timezone.utc
    )


@pytest.mark.integration
async def test_paid_renewal_extends_future_traffic_limited_subscription(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=6005)
    old_expiry = datetime.now(timezone.utc) + timedelta(days=47)
    old = await repo.create_subscription(
        user_id=user.id,
        plan="standard_3m",
        tier="standard",
        panel_username="tg_6005",
        status="limited",
        started_at=old_expiry - timedelta(days=90),
        expires_at=old_expiry,
        is_active=False,
    )
    gateway = FakeGenericPanelGateway(exists=True)

    renewed = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=gateway)
    await db_session.refresh(old)

    assert _aware(renewed.started_at) == old_expiry
    assert _aware(renewed.expires_at) == old_expiry + timedelta(days=30)
    assert gateway.modified[0]["expire_at"] == old_expiry + timedelta(days=30)
    assert old.is_active is False
    assert old.status == "limited"
    assert _aware(old.expires_at) == old_expiry
    assert gateway.reset_calls == ["tg_6005"]  # Existing purchase behavior, once.


@pytest.mark.integration
async def test_paid_renewal_does_not_revive_a_historical_limited_term(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=6006)
    now = datetime.now(timezone.utc)
    old = await repo.create_subscription(
        user_id=user.id,
        plan="standard_12m",
        tier="standard",
        panel_username="tg_6006",
        status="limited",
        started_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=300),
        is_active=False,
    )
    await repo.create_subscription(
        user_id=user.id,
        plan="standard_1m",
        tier="standard",
        panel_username="tg_6006",
        status="disabled",
        started_at=now - timedelta(days=5),
        expires_at=now + timedelta(days=20),
        is_active=False,
    )
    gateway = FakeGenericPanelGateway(exists=True)

    renewed = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=gateway)

    assert now <= _aware(renewed.started_at) <= datetime.now(timezone.utc)
    assert _aware(renewed.expires_at) == _aware(renewed.started_at) + timedelta(days=30)
    assert _aware(renewed.expires_at) < _aware(old.expires_at)
