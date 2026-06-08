from datetime import datetime, timezone

import pytest
from aioresponses import aioresponses
from yarl import URL

from services.marzban_client import (
    MarzbanClient,
    MarzbanConflictError,
    MarzbanError,
    MarzbanNotFoundError,
    _timestamp,
)


def _marzban_user_payload(**overrides):
    payload = {
        "username": "tg_1001",
        "status": "active",
        "subscription_url": "https://panel.example/sub/tg_1001/token",
        "expire": 1783036800,
        "data_limit": 10 * 1024**3,
        "used_traffic": 123,
        "lifetime_used_traffic": 456,
        "proxies": {"vless": {}, "shadowsocks": {}},
        "inbounds": {"vless": ["VLESS TCP REALITY"]},
        "links": ["vless://example"],
        "note": "Telegram user 1001",
        "online_at": None,
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
def test_timestamp_converts_datetime_to_utc_epoch():
    assert _timestamp(datetime(2026, 7, 3, tzinfo=timezone.utc)) == 1783036800
    assert _timestamp(0) == 0
    assert _timestamp(None) is None


@pytest.mark.unit
async def test_create_user_requests_token_and_sends_marzban_payload():
    client = MarzbanClient(
        base_url="https://panel.example",
        username="admin",
        password="secret",
    )
    expires_at = datetime(2026, 7, 3, tzinfo=timezone.utc)

    with aioresponses() as mocked:
        mocked.post(
            "https://panel.example/api/admin/token",
            status=200,
            payload={"access_token": "jwt-token", "token_type": "bearer"},
        )
        mocked.post(
            "https://panel.example/api/user",
            status=200,
            payload=_marzban_user_payload(),
        )

        user = await client.create_user(
            username="tg_1001",
            expire_at=expires_at,
            data_limit_bytes=10 * 1024**3,
            proxies={"vless": {}, "shadowsocks": {}},
            inbounds={"vless": ["VLESS TCP REALITY"]},
            note="Telegram user 1001",
        )

    token_request = mocked.requests[("POST", URL("https://panel.example/api/admin/token"))][0]
    assert token_request.kwargs["data"]["username"] == "admin"
    assert token_request.kwargs["data"]["password"] == "secret"

    create_request = mocked.requests[("POST", URL("https://panel.example/api/user"))][0]
    assert create_request.kwargs["headers"]["Authorization"] == "Bearer jwt-token"
    assert create_request.kwargs["json"] == {
        "username": "tg_1001",
        "proxies": {"vless": {}, "shadowsocks": {}},
        "inbounds": {"vless": ["VLESS TCP REALITY"]},
        "expire": 1783036800,
        "data_limit": 10 * 1024**3,
        "data_limit_reset_strategy": "no_reset",
        "status": "active",
        "note": "Telegram user 1001",
    }
    assert user.username == "tg_1001"
    assert user.subscription_url == "https://panel.example/sub/tg_1001/token"
    assert user.used_traffic_bytes == 123
    assert user.links == ["vless://example"]


@pytest.mark.unit
async def test_get_user_uses_existing_access_token():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    with aioresponses() as mocked:
        mocked.get("https://panel.example/api/user/tg_1001", status=200, payload=_marzban_user_payload())

        user = await client.get_user("tg_1001")

    request = mocked.requests[("GET", URL("https://panel.example/api/user/tg_1001"))][0]
    assert request.kwargs["headers"]["Authorization"] == "Bearer static-token"
    assert user.data_limit_bytes == 10 * 1024**3


@pytest.mark.unit
async def test_get_system_and_inbounds_use_marzban_contract():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    with aioresponses() as mocked:
        mocked.get("https://panel.example/api/system", status=200, payload={"version": "0.8.4"})
        mocked.get(
            "https://panel.example/api/inbounds",
            status=200,
            payload={"vless": [{"tag": "VLESS Reality 443", "tls": "reality"}]},
        )

        system = await client.get_system()
        inbounds = await client.get_inbounds()

    assert system["version"] == "0.8.4"
    assert inbounds == {"vless": [{"tag": "VLESS Reality 443", "tls": "reality"}]}


@pytest.mark.unit
async def test_relative_subscription_url_is_normalized():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    with aioresponses() as mocked:
        mocked.get(
            "https://panel.example/api/user/tg_1001",
            status=200,
            payload=_marzban_user_payload(subscription_url="/sub/tg_1001/token"),
        )

        user = await client.get_user("tg_1001")

    assert user.subscription_url == "https://panel.example/sub/tg_1001/token"


@pytest.mark.unit
async def test_modify_user_omits_none_values():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    with aioresponses() as mocked:
        mocked.put("https://panel.example/api/user/tg_1001", status=200, payload=_marzban_user_payload(status="disabled"))

        user = await client.modify_user("tg_1001", status="disabled", note=None)

    request = mocked.requests[("PUT", URL("https://panel.example/api/user/tg_1001"))][0]
    assert request.kwargs["json"] == {"status": "disabled"}
    assert user.status == "disabled"


@pytest.mark.unit
async def test_delete_user_calls_marzban_endpoint():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    with aioresponses() as mocked:
        mocked.delete("https://panel.example/api/user/tg_1001", status=200, payload={})

        assert await client.delete_user("tg_1001") is True


@pytest.mark.unit
async def test_close_is_safe_for_context_managed_sessions():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    assert await client.close() is None
    assert await client.close() is None


@pytest.mark.unit
async def test_get_user_maps_404_to_not_found():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    with aioresponses() as mocked:
        mocked.get("https://panel.example/api/user/missing", status=404, payload={"detail": "not found"})

        with pytest.raises(MarzbanNotFoundError):
            await client.get_user("missing")


@pytest.mark.unit
async def test_create_user_maps_409_to_conflict():
    client = MarzbanClient(base_url="https://panel.example", access_token="static-token")

    with aioresponses() as mocked:
        mocked.post("https://panel.example/api/user", status=409, payload={"detail": "exists"})

        with pytest.raises(MarzbanConflictError):
            await client.create_user(username="tg_1001", expire_at=0)


@pytest.mark.unit
async def test_token_response_without_access_token_raises():
    client = MarzbanClient(base_url="https://panel.example", username="admin", password="secret")

    with aioresponses() as mocked:
        mocked.post("https://panel.example/api/admin/token", status=200, payload={"token_type": "bearer"})

        with pytest.raises(MarzbanError, match="access_token"):
            await client.get_user("tg_1001")
