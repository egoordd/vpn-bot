from datetime import datetime, timezone

import pytest
from aioresponses import aioresponses
from yarl import URL

from services.panel_client import RemnawaveClient, RemnawaveError, RemnawaveNotFoundError


def _panel_user_payload(**overrides):
    payload = {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "id": 1,
        "shortUuid": "abc123",
        "username": "tg_1001",
        "status": "ACTIVE",
        "trafficLimitBytes": 10 * 1024**3,
        "trafficLimitStrategy": "NO_RESET",
        "expireAt": "2026-07-03T00:00:00Z",
        "subscriptionUrl": "https://sub.example/api/sub/abc123",
        "hwidDeviceLimit": 3,
        "userTraffic": {
            "usedTrafficBytes": 123,
            "lifetimeUsedTrafficBytes": 456,
            "onlineAt": None,
            "firstConnectedAt": None,
            "lastConnectedNodeUuid": None,
        },
    }
    payload.update(overrides)
    return payload


def _panel_node_payload(**overrides):
    payload = {
        "uuid": "22222222-2222-2222-2222-222222222222",
        "name": "premium-ams-1",
        "address": "203.0.113.10",
        "port": 2222,
        "isConnected": False,
        "isDisabled": False,
        "isConnecting": True,
        "countryCode": "NL",
        "trafficUsedBytes": 0,
        "usersOnline": 0,
    }
    payload.update(overrides)
    return payload


def _panel_host_payload(**overrides):
    payload = {
        "uuid": "33333333-3333-3333-3333-333333333333",
        "remark": "premium-ams-1",
        "address": "203.0.113.10",
        "port": 1234,
        "tag": "AUTO",
        "isDisabled": False,
        "inbound": {
            "configProfileUuid": "profile-uuid",
            "configProfileInboundUuid": "inbound-uuid",
        },
        "nodes": ["22222222-2222-2222-2222-222222222222"],
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
async def test_create_user_sends_remnawave_payload():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")
    expires_at = datetime(2026, 7, 3, tzinfo=timezone.utc)

    with aioresponses() as mocked:
        mocked.post(
            "https://panel.example/api/users",
            status=201,
            payload={"response": _panel_user_payload()},
        )

        user = await client.create_user(
            username="tg_1001",
            expire_at=expires_at,
            traffic_limit_bytes=10 * 1024**3,
            device_limit=3,
            telegram_id=1001,
            tag="standard",
        )

    request = mocked.requests[("POST", URL("https://panel.example/api/users"))][0]
    assert request.kwargs["headers"]["Authorization"] == "Bearer token"
    assert request.kwargs["json"] == {
        "username": "tg_1001",
        "status": "ACTIVE",
        "trafficLimitBytes": 10 * 1024**3,
        "trafficLimitStrategy": "MONTH",
        "expireAt": "2026-07-03T00:00:00Z",
        "tag": "STANDARD",
        "telegramId": 1001,
        "hwidDeviceLimit": 3,
    }
    assert user.username == "tg_1001"
    assert user.short_uuid == "abc123"
    assert user.usage.used_traffic_bytes == 123


@pytest.mark.unit
async def test_modify_user_requires_username_or_uuid():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with pytest.raises(ValueError):
        await client.modify_user(status="ACTIVE")


@pytest.mark.unit
async def test_get_user_maps_404_to_not_found():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.get("https://panel.example/api/users/by-username/missing", status=404, payload={"message": "not found"})

        with pytest.raises(RemnawaveNotFoundError):
            await client.get_user("missing")


@pytest.mark.unit
async def test_get_subscription_url_reads_protected_subscription_response():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.get(
            "https://panel.example/api/subscriptions/by-username/tg_1001",
            payload={"response": {"isFound": True, "subscriptionUrl": "https://sub.example/api/sub/abc123"}},
        )

        assert await client.get_subscription_url("tg_1001") == "https://sub.example/api/sub/abc123"


@pytest.mark.unit
async def test_generate_node_secret_reads_keygen_response():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.get("https://panel.example/api/keygen", payload={"response": {"pubKey": "node-secret"}})

        assert await client.generate_node_secret() == "node-secret"


@pytest.mark.unit
async def test_create_node_sends_remnawave_payload():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.post(
            "https://panel.example/api/nodes",
            status=201,
            payload={"response": _panel_node_payload()},
        )

        node = await client.create_node(
            name="premium-ams-1",
            address="203.0.113.10",
            port=2222,
            config_profile_uuid="profile-uuid",
            active_inbound_uuids=["inbound-1", "inbound-2"],
            is_traffic_tracking_active=True,
            country_code="NL",
            tags=["PREMIUM", "VULTR"],
        )

    request = mocked.requests[("POST", URL("https://panel.example/api/nodes"))][0]
    assert request.kwargs["json"] == {
        "name": "premium-ams-1",
        "address": "203.0.113.10",
        "port": 2222,
        "isTrafficTrackingActive": True,
        "countryCode": "NL",
        "configProfile": {
            "activeConfigProfileUuid": "profile-uuid",
            "activeInbounds": ["inbound-1", "inbound-2"],
        },
        "tags": ["PREMIUM", "VULTR"],
    }
    assert node.uuid == "22222222-2222-2222-2222-222222222222"
    assert node.address == "203.0.113.10"
    assert node.is_connecting is True


@pytest.mark.unit
async def test_delete_node_calls_remnawave_endpoint():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.delete("https://panel.example/api/nodes/node-uuid", status=204, payload={})

        assert await client.delete_node("node-uuid") is True


@pytest.mark.unit
async def test_list_hosts_reads_live_response_shape():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.get("https://panel.example/api/hosts", payload={"response": [_panel_host_payload()]})

        hosts = await client.list_hosts()

    assert hosts[0].uuid == "33333333-3333-3333-3333-333333333333"
    assert hosts[0].address == "203.0.113.10"
    assert hosts[0].port == 1234
    assert hosts[0].inbound_uuid == "inbound-uuid"
    assert hosts[0].node_uuids == ["22222222-2222-2222-2222-222222222222"]


@pytest.mark.unit
async def test_create_host_sends_live_remnawave_payload():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.post(
            "https://panel.example/api/hosts",
            status=201,
            payload={"response": _panel_host_payload()},
        )

        host = await client.create_host(
            remark="premium-ams-1",
            address="203.0.113.10",
            port=1234,
            config_profile_uuid="profile-uuid",
            inbound_uuid="inbound-uuid",
            node_uuids=["22222222-2222-2222-2222-222222222222"],
            tag="AUTO",
        )

    request = mocked.requests[("POST", URL("https://panel.example/api/hosts"))][0]
    assert request.kwargs["json"] == {
        "remark": "premium-ams-1",
        "address": "203.0.113.10",
        "port": 1234,
        "tag": "AUTO",
        "inbound": {
            "configProfileUuid": "profile-uuid",
            "configProfileInboundUuid": "inbound-uuid",
        },
        "nodes": ["22222222-2222-2222-2222-222222222222"],
    }
    assert host.uuid == "33333333-3333-3333-3333-333333333333"


@pytest.mark.unit
async def test_delete_host_calls_remnawave_endpoint():
    client = RemnawaveClient(base_url="https://panel.example", api_token="token")

    with aioresponses() as mocked:
        mocked.delete("https://panel.example/api/hosts/host-uuid", status=204, payload={})

        assert await client.delete_host("host-uuid") is True


@pytest.mark.unit
async def test_request_requires_token():
    client = RemnawaveClient(base_url="https://panel.example", api_token="")

    with pytest.raises(RemnawaveError):
        await client.get_user("tg_1001")


@pytest.mark.unit
def test_sanitize_tag_uppercases_and_filters():
    from services.panel_client import _sanitize_tag

    assert _sanitize_tag("trial") == "TRIAL"
    assert _sanitize_tag("standard") == "STANDARD"
    assert _sanitize_tag("premium") == "PREMIUM"
    assert _sanitize_tag("VIP") == "VIP"
    assert _sanitize_tag("a-b c") == "A_B_C"  # invalid chars -> underscore
    assert _sanitize_tag(None) is None
    assert _sanitize_tag("") is None
