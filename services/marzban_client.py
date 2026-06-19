from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

import aiohttp

# Process-wide admin-token cache keyed by panel base_url. The bot builds a fresh
# MarzbanClient per request, so without this every action would re-login (~1s on
# a slow link). Invalidated on a 401 (token expiry) and re-fetched.
_TOKEN_CACHE: dict[str, str] = {}


class MarzbanError(RuntimeError):
    pass


class MarzbanNotFoundError(MarzbanError):
    pass


class MarzbanConflictError(MarzbanError):
    pass


@dataclass(frozen=True)
class MarzbanUser:
    username: str
    status: str
    subscription_url: str
    expire: int | None
    data_limit_bytes: int
    used_traffic_bytes: int
    lifetime_used_traffic_bytes: int
    proxies: dict[str, Any]
    inbounds: dict[str, list[str]]
    links: list[str]
    note: str | None = None
    online_at: str | None = None


def _timestamp(value: datetime | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.astimezone(timezone.utc).timestamp())


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _user_from_payload(payload: dict[str, Any]) -> MarzbanUser:
    try:
        return MarzbanUser(
            username=str(payload["username"]),
            status=str(payload.get("status") or "active"),
            subscription_url=str(payload.get("subscription_url") or ""),
            expire=int(payload["expire"]) if payload.get("expire") is not None else None,
            data_limit_bytes=int(payload.get("data_limit") or 0),
            used_traffic_bytes=int(payload.get("used_traffic") or 0),
            lifetime_used_traffic_bytes=int(payload.get("lifetime_used_traffic") or 0),
            proxies=dict(payload.get("proxies") or {}),
            inbounds={str(key): list(value) for key, value in (payload.get("inbounds") or {}).items()},
            links=[str(item) for item in payload.get("links") or []],
            note=payload.get("note"),
            online_at=payload.get("online_at"),
        )
    except KeyError as exc:
        raise MarzbanError(f"Marzban user response misses field: {exc.args[0]}") from exc


class MarzbanClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        access_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: int = 15,
    ):
        app_settings = None

        def get_app_settings():
            nonlocal app_settings
            if app_settings is None:
                from config import settings

                app_settings = settings
            return app_settings

        self.base_url = (base_url if base_url is not None else get_app_settings().MARZBAN_API_URL).rstrip("/")
        if access_token is not None:
            self.access_token = access_token
        elif username is not None or password is not None:
            self.access_token = ""
        else:
            self.access_token = get_app_settings().marzban_access_token
        self.username = username if username is not None else ("" if self.access_token else get_app_settings().MARZBAN_USERNAME)
        self.password = password if password is not None else ("" if self.access_token else get_app_settings().marzban_password)
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def close(self) -> None:
        return None

    def _normalize_user(self, user: MarzbanUser) -> MarzbanUser:
        if user.subscription_url.startswith("/") and self.base_url:
            return replace(user, subscription_url=urljoin(f"{self.base_url}/", user.subscription_url))
        return user

    async def _ensure_token(self) -> str:
        if self.access_token:
            return self.access_token
        cached = _TOKEN_CACHE.get(self.base_url)
        if cached:
            self.access_token = cached
            return cached
        if not self.username or not self.password:
            raise MarzbanError("MARZBAN_ACCESS_TOKEN or MARZBAN_USERNAME/MARZBAN_PASSWORD is required")
        if not self.base_url:
            raise MarzbanError("MARZBAN_API_URL is not configured")

        url = f"{self.base_url}/api/admin/token"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(
                url,
                data={
                    "grant_type": "password",
                    "username": self.username,
                    "password": self.password,
                    "scope": "",
                },
                headers={"Accept": "application/json"},
            ) as response:
                data = await self._read_response(response)

        token = data.get("access_token") if isinstance(data, dict) else None
        if not token:
            raise MarzbanError("Marzban token response has no access_token")
        self.access_token = str(token)
        _TOKEN_CACHE[self.base_url] = self.access_token
        return self.access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if not self.base_url:
            raise MarzbanError("MARZBAN_API_URL is not configured")

        for attempt in (1, 2):
            token = await self._ensure_token()
            url = f"{self.base_url}{path}"
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=json,
                    params=_clean_payload(params or {}),
                ) as response:
                    if response.status == 401 and attempt == 1:
                        # Cached token expired — drop it and retry with a fresh login.
                        self.access_token = ""
                        _TOKEN_CACHE.pop(self.base_url, None)
                        continue
                    return await self._read_response(response)
        raise MarzbanError("Marzban authentication failed after token refresh")

    async def _read_response(self, response: aiohttp.ClientResponse) -> Any:
        if response.status == 404:
            raise MarzbanNotFoundError("Marzban resource not found")
        if response.status == 409:
            raise MarzbanConflictError("Marzban resource already exists")
        if response.status == 204:
            return {}

        try:
            data = await response.json()
        except aiohttp.ContentTypeError as exc:
            text = await response.text()
            raise MarzbanError(f"Marzban returned non-JSON response: {response.status} {text}") from exc

        if response.status >= 400:
            raise MarzbanError(f"Marzban HTTP error: {response.status} {data}")
        return data

    async def get_system(self) -> dict[str, Any]:
        response = await self._request("GET", "/api/system")
        if not isinstance(response, dict):
            raise MarzbanError(f"Unexpected get_system response: {response}")
        return response

    async def get_inbounds(self) -> dict[str, list[dict[str, Any]]]:
        response = await self._request("GET", "/api/inbounds")
        if not isinstance(response, dict):
            raise MarzbanError(f"Unexpected get_inbounds response: {response}")
        return {str(key): list(value) for key, value in response.items()}

    async def create_user(
        self,
        *,
        username: str,
        expire_at: datetime | int | None,
        data_limit_bytes: int | None = None,
        proxies: dict[str, Any] | None = None,
        inbounds: dict[str, list[str]] | None = None,
        data_limit_reset_strategy: str = "no_reset",
        status: str = "active",
        note: str | None = None,
    ) -> MarzbanUser:
        payload = _clean_payload(
            {
                "username": username,
                "proxies": proxies if proxies is not None else {},
                "inbounds": inbounds if inbounds is not None else {},
                "expire": _timestamp(expire_at),
                "data_limit": data_limit_bytes,
                "data_limit_reset_strategy": data_limit_reset_strategy,
                "status": status,
                "note": note,
            }
        )
        response = await self._request("POST", "/api/user", json=payload)
        if not isinstance(response, dict):
            raise MarzbanError(f"Unexpected create_user response: {response}")
        return self._normalize_user(_user_from_payload(response))

    async def get_user(self, username: str) -> MarzbanUser:
        response = await self._request("GET", f"/api/user/{quote(username, safe='')}")
        if not isinstance(response, dict):
            raise MarzbanError(f"Unexpected get_user response: {response}")
        return self._normalize_user(_user_from_payload(response))

    async def modify_user(
        self,
        username: str,
        *,
        expire_at: datetime | int | None = None,
        data_limit_bytes: int | None = None,
        proxies: dict[str, Any] | None = None,
        inbounds: dict[str, list[str]] | None = None,
        data_limit_reset_strategy: str | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> MarzbanUser:
        payload = _clean_payload(
            {
                "proxies": proxies,
                "inbounds": inbounds,
                "expire": _timestamp(expire_at),
                "data_limit": data_limit_bytes,
                "data_limit_reset_strategy": data_limit_reset_strategy,
                "status": status,
                "note": note,
            }
        )
        response = await self._request("PUT", f"/api/user/{quote(username, safe='')}", json=payload)
        if not isinstance(response, dict):
            raise MarzbanError(f"Unexpected modify_user response: {response}")
        return self._normalize_user(_user_from_payload(response))

    async def delete_user(self, username: str) -> bool:
        await self._request("DELETE", f"/api/user/{quote(username, safe='')}")
        return True


def build_marzban_username(telegram_id: int) -> str:
    from config import settings

    prefix = settings.MARZBAN_USERNAME_PREFIX.strip() or "tg"
    return f"{prefix}_{telegram_id}"
