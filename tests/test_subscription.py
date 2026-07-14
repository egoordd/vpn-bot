from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services.panel_client import PanelUsage, PanelUser, RemnawaveNotFoundError
from services.panel_gateway import PanelAccount, PanelUserNotFoundError
from services.payment import PLANS
from services.subscription import (
    _aware,
    activate_panel_subscription,
    activate_subscription,
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


@pytest.mark.integration
async def test_activate_subscription_unknown_plan_raises(db_session):
    with pytest.raises(ValueError):
        await activate_subscription(db_session, user_id=1, plan="unknown")


@pytest.mark.integration
async def test_activate_subscription_without_prior_subscription_starts_now(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=1, username="alice")

    before = datetime.now(timezone.utc)
    subscription = await activate_subscription(db_session, user.id, "standard_1m")
    after = datetime.now(timezone.utc)

    assert _aware(subscription.started_at) >= before - timedelta(seconds=1)
    assert _aware(subscription.started_at) <= after + timedelta(seconds=1)
    assert _aware(subscription.expires_at) == _aware(subscription.started_at) + timedelta(
        days=PLANS["standard_1m"]["days"]
    )
    assert subscription.plan == "standard_1m"
    assert subscription.is_active is True


@pytest.mark.integration
async def test_activate_subscription_accepts_legacy_plan_alias(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=11)

    subscription = await activate_subscription(db_session, user.id, "1m")

    assert subscription.plan == "standard_1m"
    assert subscription.tier == "standard"


@pytest.mark.integration
async def test_activate_subscription_stacks_existing_active_subscription(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=2)
    now = datetime.now(timezone.utc)
    old = await repo.create_subscription(
        user_id=user.id,
        plan="1m",
        started_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=10),
        is_active=True,
    )

    new_subscription = await activate_subscription(db_session, user.id, "standard_3m")
    await db_session.refresh(old)

    assert _aware(new_subscription.started_at) == _aware(old.expires_at)
    assert _aware(new_subscription.expires_at) == _aware(old.expires_at) + timedelta(
        days=PLANS["standard_3m"]["days"]
    )
    assert old.is_active is False
    assert new_subscription.is_active is True


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


class FakePanelClient:
    def __init__(self, exists: bool = False):
        self.exists = exists
        self.created: list[dict[str, object]] = []
        self.modified: list[dict[str, object]] = []

    async def get_user(self, username: str) -> PanelUser:
        if not self.exists:
            raise RemnawaveNotFoundError("missing")
        return self._panel_user(username)

    async def create_user(self, **kwargs) -> PanelUser:
        self.created.append(kwargs)
        self.exists = True
        return self._panel_user(str(kwargs["username"]))

    async def modify_user(self, **kwargs) -> PanelUser:
        self.modified.append(kwargs)
        self.exists = True
        return self._panel_user(str(kwargs["username"]))

    def _panel_user(self, username: str) -> PanelUser:
        return PanelUser(
            uuid="uuid",
            username=username,
            short_uuid="short",
            subscription_url="https://sub.example/api/sub/short",
            status="ACTIVE",
            expire_at="2026-07-03T00:00:00Z",
            traffic_limit_bytes=10 * 1024**3,
            traffic_limit_strategy="NO_RESET",
            hwid_device_limit=1,
            usage=PanelUsage(used_traffic_bytes=42, lifetime_used_traffic_bytes=42),
        )


class FakeGenericPanelGateway:
    provider = "marzban"

    def __init__(self, exists: bool = False):
        self.exists = exists
        self.created: list[dict[str, object]] = []
        self.modified: list[dict[str, object]] = []

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

    def _account(self, username: str) -> PanelAccount:
        return PanelAccount(
            username=username,
            short_uuid=username,
            subscription_url=f"https://marzban.example/sub/{username}",
            status="active",
            expire_at=1783036800,
            traffic_limit_bytes=10 * 1024**3,
            used_traffic_bytes=77,
            lifetime_used_traffic_bytes=88,
            device_limit=None,
            provider=self.provider,
        )


@pytest.mark.integration
async def test_activate_panel_subscription_creates_panel_user_and_subscription(db_session, monkeypatch):
    monkeypatch.setattr(
        "services.subscription.settings.REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS",
        "squad-1, squad-2",
    )
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=600, username="alice")
    panel = FakePanelClient(exists=False)

    subscription = await activate_panel_subscription(db_session, user.id, "trial", panel_client=panel)

    assert panel.created[0]["username"] == "tg_600"
    assert panel.created[0]["telegram_id"] == 600
    assert panel.created[0]["active_internal_squads"] == ["squad-1", "squad-2"]
    assert subscription.plan == "trial"
    assert subscription.tier == "trial"
    assert subscription.panel_username == "tg_600"
    assert subscription.sub_token == "short"
    assert subscription.traffic_limit_bytes == 10 * 1024**3
    assert subscription.traffic_used_bytes == 42
    assert subscription.device_limit == 1


@pytest.mark.integration
async def test_activate_panel_subscription_extends_existing_panel_user(db_session, monkeypatch):
    monkeypatch.setattr("services.subscription.settings.REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS", "squad-1")
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
    panel = FakePanelClient(exists=True)

    subscription = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_client=panel)
    await db_session.refresh(old)

    assert panel.created == []
    assert panel.modified[0]["username"] == "tg_601"
    assert panel.modified[0]["status"] == "ACTIVE"
    assert panel.modified[0]["active_internal_squads"] == ["squad-1"]
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


@pytest.mark.integration
async def test_standard_and_premium_coexist_independently(session_pool, monkeypatch):
    # Premium lane uses a distinct panel user and does not overwrite the
    # standard (non-premium) lane.
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import services.subscription as subscription_module
    from database.repository import Repository
    from services.subscription import activate_panel_subscription

    monkeypatch.setattr(
        subscription_module.settings,
        "MARZBAN_REGION_INBOUNDS",
        '{"ams": {"vless": ["VLESS Reality AMS"]}}',
    )

    created = []

    class FakeGateway:
        provider = "fake"

        def build_username(self, telegram_id):
            return f"tg_{telegram_id}"

        async def get_user(self, username):
            from services.panel_gateway import PanelUserNotFoundError

            raise PanelUserNotFoundError(username)

        async def create_user(self, **kwargs):
            created.append(kwargs)
            return SimpleNamespace(
                username=kwargs["username"],
                short_uuid=kwargs["username"],
                subscription_url=f"https://sub/{kwargs['username']}",
                status="active",
                expire_at=0,
                traffic_limit_bytes=None,
                used_traffic_bytes=0,
                lifetime_used_traffic_bytes=0,
                device_limit=None,
                provider="fake",
            )

        async def modify_user(self, **kwargs):
            raise AssertionError("should not modify in this test")

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=4242, username="dual")
        gw = FakeGateway()
        std = await activate_panel_subscription(session, user.id, "standard_1m", panel_gateway=gw)
        prem = await activate_panel_subscription(session, user.id, "premium_1m", panel_gateway=gw, region="ams")

        actives = await repo.list_active_subscriptions(user.id)

    usernames = {c["username"] for c in created}
    assert usernames == {"tg_4242", "tg_4242p"}
    assert std.panel_username == "tg_4242"
    assert prem.panel_username == "tg_4242p"
    # premium got the AMS inbound; standard got the default
    prem_call = next(c for c in created if c["username"] == "tg_4242p")
    assert prem_call["inbounds"] == {"vless": ["VLESS Reality AMS"]}
    # both subscriptions remain active simultaneously
    assert {s.tier for s in actives} == {"standard", "premium"}


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
