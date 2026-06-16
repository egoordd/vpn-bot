from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from config import settings
from services.marzban_client import (
    MarzbanClient,
    MarzbanConflictError,
    MarzbanError,
    MarzbanNotFoundError,
    MarzbanUser,
    build_marzban_username,
)
from services.panel_client import (
    PanelUser,
    RemnawaveClient,
    RemnawaveError,
    RemnawaveNotFoundError,
    build_panel_username,
)


class PanelGatewayError(RuntimeError):
    pass


class PanelUserNotFoundError(PanelGatewayError):
    pass


@dataclass(frozen=True)
class PanelAccount:
    username: str
    short_uuid: str
    subscription_url: str
    status: str
    expire_at: str | int | None
    traffic_limit_bytes: int | None
    used_traffic_bytes: int
    lifetime_used_traffic_bytes: int
    device_limit: int | None = None
    provider: str = ""


class PanelGateway(Protocol):
    provider: str

    def build_username(self, telegram_id: int) -> str:
        pass

    async def get_user(self, username: str) -> PanelAccount:
        pass

    async def create_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        telegram_id: int | None = None,
        status: str = "active",
        description: str | None = None,
        tag: str | None = None,
        inbounds: dict[str, list[str]] | None = None,
    ) -> PanelAccount:
        pass

    async def modify_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        status: str = "active",
        description: str | None = None,
        tag: str | None = None,
        inbounds: dict[str, list[str]] | None = None,
    ) -> PanelAccount:
        pass


class RemnawavePanelGateway:
    provider = "remnawave"

    def __init__(self, client: RemnawaveClient | Any | None = None):
        self.client = client or RemnawaveClient()

    def build_username(self, telegram_id: int) -> str:
        return build_panel_username(telegram_id)

    def _account(self, user: PanelUser) -> PanelAccount:
        return PanelAccount(
            username=user.username,
            short_uuid=user.short_uuid,
            subscription_url=user.subscription_url,
            status=user.status,
            expire_at=user.expire_at,
            traffic_limit_bytes=user.traffic_limit_bytes,
            used_traffic_bytes=user.usage.used_traffic_bytes,
            lifetime_used_traffic_bytes=user.usage.lifetime_used_traffic_bytes,
            device_limit=user.hwid_device_limit,
            provider=self.provider,
        )

    async def get_user(self, username: str) -> PanelAccount:
        try:
            return self._account(await self.client.get_user(username))
        except RemnawaveNotFoundError as exc:
            raise PanelUserNotFoundError(str(exc)) from exc
        except RemnawaveError as exc:
            raise PanelGatewayError(str(exc)) from exc

    async def create_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        telegram_id: int | None = None,
        status: str = "active",
        description: str | None = None,
        tag: str | None = None,
        inbounds: dict[str, list[str]] | None = None,
    ) -> PanelAccount:
        del inbounds  # Remnawave routes via internal squads, not Marzban inbounds.
        active_internal_squads = settings.remnawave_default_internal_squad_uuids_list or None
        try:
            user = await self.client.create_user(
                username=username,
                expire_at=expire_at,
                traffic_limit_bytes=traffic_limit_bytes,
                device_limit=device_limit,
                telegram_id=telegram_id,
                status=status.upper(),
                description=description,
                tag=tag,
                active_internal_squads=active_internal_squads,
            )
            return self._account(user)
        except RemnawaveError as exc:
            raise PanelGatewayError(str(exc)) from exc

    async def modify_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        status: str = "active",
        description: str | None = None,
        tag: str | None = None,
        inbounds: dict[str, list[str]] | None = None,
    ) -> PanelAccount:
        del inbounds  # Remnawave routes via internal squads, not Marzban inbounds.
        active_internal_squads = settings.remnawave_default_internal_squad_uuids_list or None
        try:
            user = await self.client.modify_user(
                username=username,
                expire_at=expire_at,
                traffic_limit_bytes=traffic_limit_bytes,
                device_limit=device_limit,
                status=status.upper(),
                description=description,
                tag=tag,
                active_internal_squads=active_internal_squads,
            )
            return self._account(user)
        except RemnawaveError as exc:
            raise PanelGatewayError(str(exc)) from exc


class MarzbanPanelGateway:
    provider = "marzban"

    def __init__(self, client: MarzbanClient | None = None):
        self.client = client or MarzbanClient()

    def build_username(self, telegram_id: int) -> str:
        return build_marzban_username(telegram_id)

    def _account(self, user: MarzbanUser) -> PanelAccount:
        traffic_limit = user.data_limit_bytes if user.data_limit_bytes > 0 else None
        return PanelAccount(
            username=user.username,
            short_uuid=user.username,
            subscription_url=user.subscription_url,
            status=user.status,
            expire_at=user.expire,
            traffic_limit_bytes=traffic_limit,
            used_traffic_bytes=user.used_traffic_bytes,
            lifetime_used_traffic_bytes=user.lifetime_used_traffic_bytes,
            device_limit=None,
            provider=self.provider,
        )

    async def get_user(self, username: str) -> PanelAccount:
        try:
            return self._account(await self.client.get_user(username))
        except MarzbanNotFoundError as exc:
            raise PanelUserNotFoundError(str(exc)) from exc
        except MarzbanError as exc:
            raise PanelGatewayError(str(exc)) from exc

    async def create_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        telegram_id: int | None = None,
        status: str = "active",
        description: str | None = None,
        tag: str | None = None,
        inbounds: dict[str, list[str]] | None = None,
    ) -> PanelAccount:
        del device_limit, tag
        try:
            user = await self.client.create_user(
                username=username,
                expire_at=expire_at,
                data_limit_bytes=traffic_limit_bytes,
                proxies=settings.marzban_default_proxies_dict,
                inbounds=inbounds or settings.marzban_default_inbounds_dict,
                data_limit_reset_strategy=settings.MARZBAN_DATA_LIMIT_RESET_STRATEGY,
                status=status.lower(),
                note=description or (f"Telegram user {telegram_id}" if telegram_id is not None else None),
            )
            return self._account(user)
        except MarzbanConflictError as exc:
            raise PanelGatewayError(str(exc)) from exc
        except MarzbanError as exc:
            raise PanelGatewayError(str(exc)) from exc

    async def modify_user(
        self,
        *,
        username: str,
        expire_at: datetime,
        traffic_limit_bytes: int | None = None,
        device_limit: int | None = None,
        status: str = "active",
        description: str | None = None,
        tag: str | None = None,
        inbounds: dict[str, list[str]] | None = None,
    ) -> PanelAccount:
        del device_limit, tag
        try:
            user = await self.client.modify_user(
                username,
                expire_at=expire_at,
                data_limit_bytes=traffic_limit_bytes,
                proxies=settings.marzban_default_proxies_dict,
                inbounds=inbounds or settings.marzban_default_inbounds_dict,
                data_limit_reset_strategy=settings.MARZBAN_DATA_LIMIT_RESET_STRATEGY,
                status=status.lower(),
                note=description,
            )
            return self._account(user)
        except MarzbanError as exc:
            raise PanelGatewayError(str(exc)) from exc


def panel_provider() -> str:
    return settings.PANEL_PROVIDER.strip().lower() or "remnawave"


def is_panel_configured() -> bool:
    provider = panel_provider()
    if provider == "remnawave":
        return bool(settings.REMNAWAVE_API_URL.strip() and settings.remnawave_api_token.strip())
    if provider == "marzban":
        return bool(
            settings.MARZBAN_API_URL.strip()
            and (
                settings.marzban_access_token.strip()
                or (settings.MARZBAN_USERNAME.strip() and settings.marzban_password.strip())
            )
        )
    return False


def get_panel_gateway() -> PanelGateway:
    provider = panel_provider()
    if provider == "remnawave":
        return RemnawavePanelGateway()
    if provider == "marzban":
        return MarzbanPanelGateway()
    raise PanelGatewayError(f"Unsupported PANEL_PROVIDER: {settings.PANEL_PROVIDER}")
