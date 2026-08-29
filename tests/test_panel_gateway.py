from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from services.marzban_client import MarzbanNotFoundError, MarzbanUser
from services.panel_client import PanelUsage, PanelUser, RemnawaveNotFoundError
from services.panel_gateway import (
    MarzbanPanelGateway,
    PanelUserNotFoundError,
    RemnawavePanelGateway,
    get_panel_gateway,
    is_panel_configured,
)


class FakeRemnawaveClient:
    def __init__(self):
        self.created: list[dict[str, object]] = []

    async def get_user(self, username: str) -> PanelUser:
        if username == "missing":
            raise RemnawaveNotFoundError("missing")
        return self._user(username)

    async def create_user(self, **kwargs) -> PanelUser:
        self.created.append(kwargs)
        return self._user(str(kwargs["username"]))

    def _user(self, username: str) -> PanelUser:
        return PanelUser(
            uuid="uuid",
            username=username,
            short_uuid="short",
            subscription_url="https://sub.example/api/sub/short",
            status="ACTIVE",
            expire_at="2026-07-03T00:00:00Z",
            traffic_limit_bytes=10 * 1024**3,
            traffic_limit_strategy="NO_RESET",
            hwid_device_limit=3,
            usage=PanelUsage(used_traffic_bytes=123, lifetime_used_traffic_bytes=456),
        )


class FakeMarzbanClient:
    def __init__(self):
        self.created: list[dict[str, object]] = []
        self.modified: list[dict[str, object]] = []
        self.reset_calls: list[str] = []

    async def get_user(self, username: str) -> MarzbanUser:
        if username == "missing":
            raise MarzbanNotFoundError("missing")
        return self._user(username)

    async def create_user(self, **kwargs) -> MarzbanUser:
        self.created.append(kwargs)
        return self._user(str(kwargs["username"]))

    async def modify_user(self, username: str, **kwargs) -> MarzbanUser:
        self.modified.append({"username": username, **kwargs})
        return self._user(username, status=str(kwargs.get("status") or "active"))

    async def reset_user_data_usage(self, username: str) -> MarzbanUser:
        if username == "missing":
            raise MarzbanNotFoundError("missing")
        self.reset_calls.append(username)
        return self._user(username, used_traffic_bytes=0)

    def _user(self, username: str, status: str = "active", used_traffic_bytes: int = 123) -> MarzbanUser:
        return MarzbanUser(
            username=username,
            status=status,
            subscription_url=f"https://panel.example/sub/{username}",
            expire=1783036800,
            data_limit_bytes=10 * 1024**3,
            used_traffic_bytes=used_traffic_bytes,
            lifetime_used_traffic_bytes=456,
            proxies={"vless": {}},
            inbounds={"vless": ["VLESS TCP REALITY"]},
            links=["vless://example"],
        )


@pytest.mark.unit
async def test_remnawave_gateway_maps_panel_user_and_payload(monkeypatch):
    monkeypatch.setattr(
        "services.panel_gateway.settings.REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS",
        "squad-1,squad-2",
    )
    client = FakeRemnawaveClient()
    gateway = RemnawavePanelGateway(client)

    account = await gateway.create_user(
        username="tg_100",
        expire_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        traffic_limit_bytes=10 * 1024**3,
        device_limit=3,
        telegram_id=100,
        status="active",
        description="note",
        tag="standard",
    )

    assert account.username == "tg_100"
    assert account.short_uuid == "short"
    assert account.used_traffic_bytes == 123
    assert account.device_limit == 3
    assert client.created[0]["status"] == "ACTIVE"
    assert client.created[0]["active_internal_squads"] == ["squad-1", "squad-2"]


@pytest.mark.unit
async def test_remnawave_gateway_maps_not_found():
    gateway = RemnawavePanelGateway(FakeRemnawaveClient())

    with pytest.raises(PanelUserNotFoundError):
        await gateway.get_user("missing")


@pytest.mark.unit
async def test_marzban_gateway_uses_default_proxy_config(monkeypatch):
    monkeypatch.setattr("services.panel_gateway.settings.MARZBAN_DEFAULT_PROXIES", '{"vless":{}}')
    monkeypatch.setattr("services.panel_gateway.settings.MARZBAN_DEFAULT_INBOUNDS", '{"vless":["VLESS TCP REALITY"]}')
    monkeypatch.setattr("services.panel_gateway.settings.MARZBAN_DATA_LIMIT_RESET_STRATEGY", "month")
    client = FakeMarzbanClient()
    gateway = MarzbanPanelGateway(client)

    account = await gateway.create_user(
        username="tg_100",
        expire_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        traffic_limit_bytes=10 * 1024**3,
        device_limit=3,
        telegram_id=100,
        status="active",
        description="note",
        tag="standard",
    )

    assert account.username == "tg_100"
    assert account.short_uuid == "tg_100"
    assert account.provider == "marzban"
    assert account.device_limit is None
    assert client.created[0]["proxies"] == {"vless": {}}
    assert client.created[0]["inbounds"] == {"vless": ["VLESS TCP REALITY"]}
    assert client.created[0]["data_limit_reset_strategy"] == "month"


@pytest.mark.unit
async def test_marzban_gateway_maps_not_found():
    gateway = MarzbanPanelGateway(FakeMarzbanClient())

    with pytest.raises(PanelUserNotFoundError):
        await gateway.get_user("missing")


@pytest.mark.unit
def test_panel_configuration_selects_provider(monkeypatch):
    monkeypatch.setattr("services.panel_gateway.settings.PANEL_PROVIDER", "marzban")
    monkeypatch.setattr("services.panel_gateway.settings.MARZBAN_API_URL", "https://panel.example")
    monkeypatch.setattr("services.panel_gateway.settings.MARZBAN_ACCESS_TOKEN", SecretStr("token"))

    assert is_panel_configured() is True
    assert isinstance(get_panel_gateway(), MarzbanPanelGateway)

    monkeypatch.setattr("services.panel_gateway.settings.PANEL_PROVIDER", "remnawave")
    monkeypatch.setattr("services.panel_gateway.settings.REMNAWAVE_API_URL", "https://remna.example")
    monkeypatch.setattr("services.panel_gateway.settings.REMNAWAVE_API_TOKEN", SecretStr("token"))

    assert is_panel_configured() is True
    assert isinstance(get_panel_gateway(), RemnawavePanelGateway)


@pytest.mark.unit
async def test_marzban_gateway_lets_the_tariff_decide_the_reset_strategy(monkeypatch):
    """The per-user flag must beat the global setting.

    A stale MARZBAN_DATA_LIMIT_RESET_STRATEGY in .env is what sold one-shot
    quotas for months, so the tariff's own answer has to win outright.
    """
    monkeypatch.setattr("services.panel_gateway.settings.MARZBAN_DATA_LIMIT_RESET_STRATEGY", "no_reset")
    client = FakeMarzbanClient()
    gateway = MarzbanPanelGateway(client)
    expires_at = datetime(2026, 7, 3, tzinfo=timezone.utc)

    await gateway.create_user(username="tg_100", expire_at=expires_at, traffic_resets_monthly=True)
    await gateway.modify_user(username="tg_100", expire_at=expires_at, traffic_resets_monthly=False)

    assert client.created[0]["data_limit_reset_strategy"] == "month"
    assert client.modified[0]["data_limit_reset_strategy"] == "no_reset"


@pytest.mark.unit
async def test_marzban_gateway_falls_back_to_the_setting_when_unspecified(monkeypatch):
    monkeypatch.setattr("services.panel_gateway.settings.MARZBAN_DATA_LIMIT_RESET_STRATEGY", "week")
    client = FakeMarzbanClient()
    gateway = MarzbanPanelGateway(client)

    await gateway.create_user(username="tg_100", expire_at=datetime(2026, 7, 3, tzinfo=timezone.utc))

    assert client.created[0]["data_limit_reset_strategy"] == "week"


@pytest.mark.unit
async def test_marzban_gateway_reset_traffic_zeroes_the_counter():
    client = FakeMarzbanClient()
    gateway = MarzbanPanelGateway(client)

    account = await gateway.reset_traffic("tg_100")

    assert client.reset_calls == ["tg_100"]
    assert account.used_traffic_bytes == 0


@pytest.mark.unit
async def test_marzban_gateway_reset_traffic_maps_not_found():
    gateway = MarzbanPanelGateway(FakeMarzbanClient())

    with pytest.raises(PanelUserNotFoundError):
        await gateway.reset_traffic("missing")


@pytest.mark.unit
async def test_remnawave_gateway_lets_the_tariff_decide_the_reset_strategy(monkeypatch):
    monkeypatch.setattr("services.panel_gateway.settings.REMNAWAVE_DEFAULT_TRAFFIC_RESET_STRATEGY", "NO_RESET")
    client = FakeRemnawaveClient()
    gateway = RemnawavePanelGateway(client)

    await gateway.create_user(
        username="tg_100",
        expire_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        traffic_resets_monthly=True,
    )

    assert client.created[0]["traffic_limit_strategy"] == "MONTH"
