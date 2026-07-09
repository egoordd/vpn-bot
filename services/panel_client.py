from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import aiohttp

from config import settings


_TAG_INVALID_RE = re.compile(r"[^A-Z0-9_]")


def _sanitize_tag(tag: str | None) -> str | None:
    """Remnawave requires user tags to be UPPERCASE letters, digits, underscores.
    Tier names come in lowercase (trial/standard/premium), so normalise them."""
    if not tag:
        return None
    cleaned = _TAG_INVALID_RE.sub("_", tag.upper())
    return cleaned or None


class RemnawaveError(RuntimeError):
    pass


class RemnawaveNotFoundError(RemnawaveError):
    pass


@dataclass(frozen=True)
class PanelUsage:
    used_traffic_bytes: int
    lifetime_used_traffic_bytes: int
    online_at: str | None = None
    first_connected_at: str | None = None
    last_connected_node_uuid: str | None = None


@dataclass(frozen=True)
class PanelUser:
    uuid: str
    username: str
    short_uuid: str
    subscription_url: str
    status: str
    expire_at: str
    traffic_limit_bytes: int | None
    traffic_limit_strategy: str | None
    hwid_device_limit: int | None
    usage: PanelUsage


@dataclass(frozen=True)
class PanelNode:
    uuid: str
    name: str
    address: str
    port: int | None
    is_connected: bool
    is_disabled: bool
    is_connecting: bool
    country_code: str
    traffic_used_bytes: int | None = None
    users_online: int | None = None


@dataclass(frozen=True)
class PanelHost:
    uuid: str
    remark: str
    address: str
    port: int
    config_profile_uuid: str
    inbound_uuid: str
    node_uuids: list[str]
    tag: str | None = None
    is_disabled: bool = False


def _format_remnawave_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _unwrap_response(data: Any) -> Any:
    if isinstance(data, dict) and "response" in data:
        return data["response"]
    return data


def _usage_from_payload(payload: dict[str, Any]) -> PanelUsage:
    traffic = payload.get("userTraffic") or {}
    return PanelUsage(
        used_traffic_bytes=int(traffic.get("usedTrafficBytes") or 0),
        lifetime_used_traffic_bytes=int(traffic.get("lifetimeUsedTrafficBytes") or 0),
        online_at=traffic.get("onlineAt"),
        first_connected_at=traffic.get("firstConnectedAt"),
        last_connected_node_uuid=traffic.get("lastConnectedNodeUuid"),
    )


def _user_from_payload(payload: dict[str, Any]) -> PanelUser:
    try:
        return PanelUser(
            uuid=str(payload["uuid"]),
            username=str(payload["username"]),
            short_uuid=str(payload["shortUuid"]),
            subscription_url=str(payload["subscriptionUrl"]),
            status=str(payload.get("status") or "ACTIVE"),
            expire_at=str(payload["expireAt"]),
            traffic_limit_bytes=(
                int(payload["trafficLimitBytes"]) if payload.get("trafficLimitBytes") is not None else None
            ),
            traffic_limit_strategy=payload.get("trafficLimitStrategy"),
            hwid_device_limit=(
                int(payload["hwidDeviceLimit"]) if payload.get("hwidDeviceLimit") is not None else None
            ),
            usage=_usage_from_payload(payload),
        )
    except KeyError as exc:
        raise RemnawaveError(f"Remnawave user response misses field: {exc.args[0]}") from exc


def _node_from_payload(payload: dict[str, Any]) -> PanelNode:
    try:
        return PanelNode(
            uuid=str(payload["uuid"]),
            name=str(payload["name"]),
            address=str(payload["address"]),
            port=int(payload["port"]) if payload.get("port") is not None else None,
            is_connected=bool(payload.get("isConnected")),
            is_disabled=bool(payload.get("isDisabled")),
            is_connecting=bool(payload.get("isConnecting")),
            country_code=str(payload.get("countryCode") or "XX"),
            traffic_used_bytes=(
                int(payload["trafficUsedBytes"]) if payload.get("trafficUsedBytes") is not None else None
            ),
            users_online=int(payload["usersOnline"]) if payload.get("usersOnline") is not None else None,
        )
    except KeyError as exc:
        raise RemnawaveError(f"Remnawave node response misses field: {exc.args[0]}") from exc


def _host_from_payload(payload: dict[str, Any]) -> PanelHost:
    inbound = payload.get("inbound") or {}
    try:
        return PanelHost(
            uuid=str(payload["uuid"]),
            remark=str(payload.get("remark") or ""),
            address=str(payload["address"]),
            port=int(payload["port"]),
            config_profile_uuid=str(inbound["configProfileUuid"]),
            inbound_uuid=str(inbound["configProfileInboundUuid"]),
            node_uuids=[str(item) for item in payload.get("nodes") or []],
            tag=payload.get("tag"),
            is_disabled=bool(payload.get("isDisabled")),
        )
    except KeyError as exc:
        raise RemnawaveError(f"Remnawave host response misses field: {exc.args[0]}") from exc


class RemnawaveClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout_seconds: int = 15,
    ):
        self.base_url = (base_url if base_url is not None else settings.REMNAWAVE_API_URL).rstrip("/")
        self.api_token = api_token if api_token is not None else settings.remnawave_api_token
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        if not self.api_token:
            raise RemnawaveError("REMNAWAVE_API_TOKEN is not configured")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if not self.base_url:
            raise RemnawaveError("REMNAWAVE_API_URL is not configured")

        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.request(
                method.upper(),
                url,
                headers=self._headers(),
                json=json,
                params=_clean_payload(params or {}),
            ) as response:
                data = await self._read_response(response)

        return _unwrap_response(data)

    async def _read_response(self, response: aiohttp.ClientResponse) -> Any:
        if response.status == 404:
            raise RemnawaveNotFoundError("Remnawave resource not found")
        if response.status == 204:
            return {}

        try:
            data = await response.json()
        except aiohttp.ContentTypeError as exc:
            text = await response.text()
            raise RemnawaveError(f"Remnawave returned non-JSON response: {response.status} {text}") from exc

        if response.status >= 400:
            raise RemnawaveError(f"Remnawave HTTP error: {response.status} {data}")
        return data

    async def create_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        telegram_id: int | None = None,
        status: str = "ACTIVE",
        traffic_limit_strategy: str | None = None,
        active_internal_squads: list[str] | None = None,
        external_squad_uuid: str | None = None,
        description: str | None = None,
        tag: str | None = None,
    ) -> PanelUser:
        payload = _clean_payload(
            {
                "username": username,
                "status": status,
                "trafficLimitBytes": traffic_limit_bytes,
                "trafficLimitStrategy": traffic_limit_strategy or settings.REMNAWAVE_DEFAULT_TRAFFIC_RESET_STRATEGY,
                "expireAt": _format_remnawave_datetime(expire_at),
                "description": description,
                "tag": _sanitize_tag(tag),
                "telegramId": telegram_id,
                "hwidDeviceLimit": device_limit,
                "activeInternalSquads": active_internal_squads,
                "externalSquadUuid": external_squad_uuid,
            }
        )
        response = await self._request("POST", "/api/users", json=payload)
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected create_user response: {response}")
        return _user_from_payload(response)

    async def get_user(self, username: str) -> PanelUser:
        response = await self._request("GET", f"/api/users/by-username/{quote(username, safe='')}")
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected get_user response: {response}")
        return _user_from_payload(response)

    async def get_user_by_uuid(self, uuid: str) -> PanelUser:
        response = await self._request("GET", f"/api/users/{quote(uuid, safe='')}")
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected get_user_by_uuid response: {response}")
        return _user_from_payload(response)

    async def modify_user(
        self,
        *,
        username: str | None = None,
        uuid: str | None = None,
        expire_at: datetime | None = None,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        status: str | None = None,
        traffic_limit_strategy: str | None = None,
        active_internal_squads: list[str] | None = None,
        external_squad_uuid: str | None = None,
        description: str | None = None,
        tag: str | None = None,
        telegram_id: int | None = None,
    ) -> PanelUser:
        if not username and not uuid:
            raise ValueError("username or uuid is required")

        payload = _clean_payload(
            {
                "username": username,
                "uuid": uuid,
                "status": status,
                "trafficLimitBytes": traffic_limit_bytes,
                "trafficLimitStrategy": traffic_limit_strategy,
                "expireAt": _format_remnawave_datetime(expire_at) if expire_at else None,
                "description": description,
                "tag": _sanitize_tag(tag),
                "telegramId": telegram_id,
                "hwidDeviceLimit": device_limit,
                "activeInternalSquads": active_internal_squads,
                "externalSquadUuid": external_squad_uuid,
            }
        )
        response = await self._request("PATCH", "/api/users", json=payload)
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected modify_user response: {response}")
        return _user_from_payload(response)

    async def delete_user(self, uuid: str) -> bool:
        await self._request("DELETE", f"/api/users/{quote(uuid, safe='')}")
        return True

    async def get_usage(self, username: str) -> PanelUsage:
        user = await self.get_user(username)
        return user.usage

    async def get_subscription_url(self, username: str) -> str:
        response = await self._request("GET", f"/api/subscriptions/by-username/{quote(username, safe='')}")
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected get_subscription_url response: {response}")
        subscription_url = response.get("subscriptionUrl")
        if not subscription_url:
            raise RemnawaveError("Remnawave subscription response has no subscriptionUrl")
        return str(subscription_url)

    async def generate_node_secret(self) -> str:
        response = await self._request("GET", "/api/keygen")
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected generate_node_secret response: {response}")
        pub_key = response.get("pubKey")
        if not pub_key:
            raise RemnawaveError("Remnawave keygen response has no pubKey")
        return str(pub_key)

    async def create_node(
        self,
        *,
        name: str,
        address: str,
        config_profile_uuid: str,
        active_inbound_uuids: list[str],
        port: int | None = None,
        is_traffic_tracking_active: bool = False,
        traffic_limit_bytes: int | None = None,
        notify_percent: int | None = None,
        traffic_reset_day: int | None = None,
        country_code: str = "XX",
        consumption_multiplier: float | None = None,
        provider_uuid: str | None = None,
        tags: list[str] | None = None,
        active_plugin_uuid: str | None = None,
    ) -> PanelNode:
        payload = _clean_payload(
            {
                "name": name,
                "address": address,
                "port": port,
                "isTrafficTrackingActive": is_traffic_tracking_active,
                "trafficLimitBytes": traffic_limit_bytes,
                "notifyPercent": notify_percent,
                "trafficResetDay": traffic_reset_day,
                "countryCode": country_code,
                "consumptionMultiplier": consumption_multiplier,
                "configProfile": {
                    "activeConfigProfileUuid": config_profile_uuid,
                    "activeInbounds": active_inbound_uuids,
                },
                "providerUuid": provider_uuid,
                "tags": tags,
                "activePluginUuid": active_plugin_uuid,
            }
        )
        response = await self._request("POST", "/api/nodes", json=payload)
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected create_node response: {response}")
        return _node_from_payload(response)

    async def delete_node(self, uuid: str) -> bool:
        await self._request("DELETE", f"/api/nodes/{quote(uuid, safe='')}")
        return True

    async def list_hosts(self) -> list[PanelHost]:
        response = await self._request("GET", "/api/hosts")
        if not isinstance(response, list):
            raise RemnawaveError(f"Unexpected list_hosts response: {response}")
        return [_host_from_payload(item) for item in response if isinstance(item, dict)]

    async def create_host(
        self,
        *,
        remark: str,
        address: str,
        port: int,
        config_profile_uuid: str,
        inbound_uuid: str,
        node_uuids: list[str],
        tag: str | None = None,
    ) -> PanelHost:
        payload = _clean_payload(
            {
                "remark": remark,
                "address": address,
                "port": port,
                "tag": _sanitize_tag(tag),
                "inbound": {
                    "configProfileUuid": config_profile_uuid,
                    "configProfileInboundUuid": inbound_uuid,
                },
                "nodes": node_uuids,
            }
        )
        response = await self._request("POST", "/api/hosts", json=payload)
        if not isinstance(response, dict):
            raise RemnawaveError(f"Unexpected create_host response: {response}")
        return _host_from_payload(response)

    async def delete_host(self, uuid: str) -> bool:
        await self._request("DELETE", f"/api/hosts/{quote(uuid, safe='')}")
        return True


def build_panel_username(telegram_id: int) -> str:
    prefix = settings.REMNAWAVE_USERNAME_PREFIX.strip() or "tg"
    return f"{prefix}_{telegram_id}"
