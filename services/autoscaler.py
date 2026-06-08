from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Node
from database.repository import Repository
from services.panel_client import PanelHost, PanelNode, RemnawaveClient
from services.tariffs import PREMIUM_REGIONS

logger = logging.getLogger(__name__)


class VultrError(RuntimeError):
    pass


class AutoscalerError(RuntimeError):
    pass


@dataclass(frozen=True)
class VultrInstance:
    id: str
    label: str
    region: str
    plan: str
    status: str
    main_ip: str


@dataclass(frozen=True)
class ProvisionNodeRequest:
    tier: str = "premium"
    region: str | None = None
    capacity: int | None = None
    plan: str | None = None
    os_id: int | None = None
    name: str | None = None
    country_code: str | None = None
    config_profile_uuid: str | None = None
    active_inbound_uuids: list[str] | None = None
    node_port: int | None = None
    host_port: int | None = None
    host_tag: str | None = None
    create_hosts: bool = True
    ssh_key_ids: list[str] | None = None
    tags: list[str] | None = None
    enable_ipv6: bool = True
    provider_uuid: str | None = None


@dataclass(frozen=True)
class StaticNodeRegistration:
    ip_address: str
    panel_node_id: str
    region: str = "ams"
    tier: str = "premium"
    capacity: int = 50
    name: str | None = None
    status: str = "active"
    current_users: int | None = None
    static_ips: list[str] | None = None


@dataclass
class AutoscalePoolResult:
    checked_regions: int = 0
    provisioned_node_ids: list[int] = field(default_factory=list)
    decommissioned_node_ids: list[int] = field(default_factory=list)

    @property
    def provisioned_count(self) -> int:
        return len(self.provisioned_node_ids)

    @property
    def decommissioned_count(self) -> int:
        return len(self.decommissioned_node_ids)


@dataclass(frozen=True)
class _ResolvedProvisioning:
    tier: str
    region: str
    capacity: int
    plan: str
    os_id: int
    name: str
    country_code: str
    config_profile_uuid: str
    active_inbound_uuids: list[str]
    node_port: int
    host_port: int
    host_tag: str | None
    create_hosts: bool
    ssh_key_ids: list[str]
    tags: list[str]
    enable_ipv6: bool
    provider_uuid: str | None


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _node_ref(node: Node) -> str:
    return node.panel_node_id or f"db:{node.id}"


async def _get_node_by_ref(repo: Repository, node_ref: str) -> Node | None:
    if node_ref.startswith("db:"):
        try:
            return await repo.get_node(int(node_ref.removeprefix("db:")))
        except ValueError:
            return None
    node = await repo.get_node_by_panel_node_id(node_ref)
    if node is not None:
        return node
    if node_ref.isdigit():
        return await repo.get_node(int(node_ref))
    return None


def _instance_from_payload(payload: dict[str, Any]) -> VultrInstance:
    try:
        return VultrInstance(
            id=str(payload["id"]),
            label=str(payload.get("label") or ""),
            region=str(payload.get("region") or ""),
            plan=str(payload.get("plan") or ""),
            status=str(payload.get("status") or ""),
            main_ip=str(payload.get("main_ip") or ""),
        )
    except KeyError as exc:
        raise VultrError(f"Vultr instance response misses field: {exc.args[0]}") from exc


def _indent(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else prefix.rstrip() for line in text.splitlines())


def build_remnawave_node_cloud_init(
    secret_key: str,
    *,
    node_port: int = 2222,
    image: str = "remnawave/node:latest",
) -> str:
    compose = "\n".join(
        [
            "services:",
            "  remnanode:",
            "    container_name: remnanode",
            "    hostname: remnanode",
            f"    image: {image}",
            "    restart: always",
            "    network_mode: host",
            "    environment:",
            f"      NODE_PORT: {node_port}",
            f"      SECRET_KEY: {json.dumps(secret_key)}",
            "",
        ]
    )
    return "\n".join(
        [
            "#cloud-config",
            "package_update: true",
            "write_files:",
            "  - path: /tmp/remnawave-node-compose.yml",
            "    permissions: '0600'",
            "    owner: root:root",
            "    content: |",
            _indent(compose, "      "),
            "runcmd:",
            '  - [ sh, -c, "curl -fsSL https://get.docker.com | sh" ]',
            '  - [ sh, -c, "mkdir -p /opt/remnanode && mv /tmp/remnawave-node-compose.yml /opt/remnanode/docker-compose.yml" ]',
            '  - [ sh, -c, "cd /opt/remnanode && docker compose up -d" ]',
            "",
        ]
    )


class VultrClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout_seconds: int = 15,
    ):
        self.base_url = (base_url if base_url is not None else settings.VULTR_API_URL).rstrip("/")
        self.api_token = api_token if api_token is not None else settings.vultr_api_token
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        if not self.api_token:
            raise VultrError("VULTR_API_TOKEN is not configured")
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
        json_payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if not self.base_url:
            raise VultrError("VULTR_API_URL is not configured")

        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.request(
                method.upper(),
                url,
                headers=self._headers(),
                json=json_payload,
                params=_clean_payload(params or {}),
            ) as response:
                return await self._read_response(response)

    async def _read_response(self, response: aiohttp.ClientResponse) -> Any:
        if response.status == 204:
            return {}

        try:
            data = await response.json()
        except aiohttp.ContentTypeError as exc:
            text = await response.text()
            raise VultrError(f"Vultr returned non-JSON response: {response.status} {text}") from exc

        if response.status >= 400:
            raise VultrError(f"Vultr HTTP error: {response.status} {data}")
        return data

    async def create_instance(
        self,
        *,
        region: str,
        plan: str,
        os_id: int,
        label: str,
        user_data: str,
        ssh_key_ids: list[str] | None = None,
        tags: list[str] | None = None,
        enable_ipv6: bool = True,
    ) -> VultrInstance:
        encoded_user_data = base64.b64encode(user_data.encode("utf-8")).decode("ascii")
        payload = _clean_payload(
            {
                "region": region,
                "plan": plan,
                "os_id": os_id,
                "label": label,
                "user_data": encoded_user_data,
                "sshkey_id": ssh_key_ids or None,
                "tags": tags or None,
                "enable_ipv6": enable_ipv6,
            }
        )
        response = await self._request("POST", "/instances", json_payload=payload)
        if not isinstance(response, dict) or not isinstance(response.get("instance"), dict):
            raise VultrError(f"Unexpected create_instance response: {response}")
        return _instance_from_payload(response["instance"])

    async def get_instance(self, instance_id: str) -> VultrInstance:
        response = await self._request("GET", f"/instances/{instance_id}")
        if not isinstance(response, dict) or not isinstance(response.get("instance"), dict):
            raise VultrError(f"Unexpected get_instance response: {response}")
        return _instance_from_payload(response["instance"])

    async def wait_for_main_ip(
        self,
        instance_id: str,
        *,
        attempts: int = 30,
        delay_seconds: float = 10,
    ) -> VultrInstance:
        last_instance: VultrInstance | None = None
        for attempt in range(attempts):
            last_instance = await self.get_instance(instance_id)
            if last_instance.main_ip:
                return last_instance
            if attempt < attempts - 1:
                await asyncio.sleep(delay_seconds)
        raise VultrError(f"Vultr instance {instance_id} has no main_ip after {attempts} attempts")

    async def delete_instance(self, instance_id: str) -> bool:
        await self._request("DELETE", f"/instances/{instance_id}")
        return True


def _resolve_request(request: ProvisionNodeRequest) -> _ResolvedProvisioning:
    region = request.region or settings.VULTR_DEFAULT_REGION
    plan = request.plan or settings.VULTR_DEFAULT_PLAN
    os_id = request.os_id if request.os_id is not None else settings.VULTR_DEFAULT_OS_ID
    capacity = request.capacity if request.capacity is not None else settings.VULTR_NODE_CAPACITY
    node_port = request.node_port if request.node_port is not None else settings.REMNAWAVE_NODE_PORT
    config_profile_uuid = request.config_profile_uuid or settings.REMNAWAVE_NODE_CONFIG_PROFILE_UUID
    active_inbound_uuids = request.active_inbound_uuids or settings.remnawave_node_inbound_uuids_list
    country_code = request.country_code or settings.REMNAWAVE_NODE_COUNTRY_CODE
    host_port = request.host_port if request.host_port is not None else settings.REMNAWAVE_HOST_PORT
    host_tag = request.host_tag if request.host_tag is not None else settings.REMNAWAVE_HOST_TAG
    ssh_key_ids = request.ssh_key_ids if request.ssh_key_ids is not None else settings.vultr_ssh_key_ids_list
    tags = request.tags or [request.tier.upper(), "VULTR"]
    name = request.name or f"{settings.VULTR_NODE_LABEL_PREFIX}-{request.tier}-{region}-{int(time.time())}"

    missing = []
    if not region:
        missing.append("VULTR_DEFAULT_REGION")
    if not plan:
        missing.append("VULTR_DEFAULT_PLAN")
    if not os_id:
        missing.append("VULTR_DEFAULT_OS_ID")
    if capacity <= 0:
        missing.append("VULTR_NODE_CAPACITY")
    if not config_profile_uuid:
        missing.append("REMNAWAVE_NODE_CONFIG_PROFILE_UUID")
    if not active_inbound_uuids:
        missing.append("REMNAWAVE_NODE_INBOUND_UUIDS")
    if request.create_hosts and host_port <= 0:
        missing.append("REMNAWAVE_HOST_PORT")
    if missing:
        raise AutoscalerError(f"Autoscaler provisioning settings are missing: {', '.join(missing)}")

    return _ResolvedProvisioning(
        tier=request.tier,
        region=region,
        capacity=capacity,
        plan=plan,
        os_id=os_id,
        name=name,
        country_code=country_code,
        config_profile_uuid=config_profile_uuid,
        active_inbound_uuids=active_inbound_uuids,
        node_port=node_port,
        host_port=host_port,
        host_tag=host_tag.strip() or None,
        create_hosts=request.create_hosts,
        ssh_key_ids=ssh_key_ids,
        tags=tags,
        enable_ipv6=request.enable_ipv6,
        provider_uuid=request.provider_uuid,
    )


async def _create_hosts_for_node(
    panel: RemnawaveClient,
    *,
    resolved: _ResolvedProvisioning,
    panel_node: PanelNode,
    address: str,
) -> list[PanelHost]:
    if not resolved.create_hosts:
        return []

    created_hosts: list[PanelHost] = []
    has_multiple_inbounds = len(resolved.active_inbound_uuids) > 1
    for inbound_uuid in resolved.active_inbound_uuids:
        suffix = f"-{inbound_uuid[:8]}" if has_multiple_inbounds else ""
        created_hosts.append(
            await panel.create_host(
                remark=f"{resolved.name}{suffix}",
                address=address,
                port=resolved.host_port,
                config_profile_uuid=resolved.config_profile_uuid,
                inbound_uuid=inbound_uuid,
                node_uuids=[panel_node.uuid],
                tag=resolved.host_tag,
            )
        )
    return created_hosts


async def _delete_hosts_for_node(panel: RemnawaveClient, panel_node_uuid: str) -> list[str]:
    deleted_host_uuids: list[str] = []
    for host in await panel.list_hosts():
        if panel_node_uuid not in host.node_uuids:
            continue
        await panel.delete_host(host.uuid)
        deleted_host_uuids.append(host.uuid)
    return deleted_host_uuids


async def register_static_node(session: AsyncSession, request: StaticNodeRegistration) -> Node:
    if request.capacity <= 0:
        raise AutoscalerError("Static node capacity must be positive")
    if not request.ip_address.strip():
        raise AutoscalerError("Static node IP address is required")
    if not request.panel_node_id.strip():
        raise AutoscalerError("Static node panel_node_id is required")

    repo = Repository(session)
    node = await repo.get_node_by_panel_node_id(request.panel_node_id)
    if node is None:
        existing_nodes = await repo.list_nodes()
        node = next((item for item in existing_nodes if item.ip_address == request.ip_address), None)

    values: dict[str, Any] = {
        "tier": request.tier,
        "capacity": request.capacity,
        "region": request.region,
        "provider": "manual",
        "provider_instance_id": None,
        "ip_address": request.ip_address,
        "panel_node_id": request.panel_node_id,
        "static_ips": list(request.static_ips or []),
        "status": request.status,
        "name": request.name,
    }
    if request.current_users is not None:
        values["current_users"] = request.current_users

    if node is not None:
        return await repo.update_node(node.id, **values) or node

    current_users = int(values.pop("current_users", 0))
    return await repo.create_node(
        current_users=current_users,
        **values,
    )


async def provision_vultr_node(
    session: AsyncSession,
    request: ProvisionNodeRequest | None = None,
    *,
    vultr_client: VultrClient | None = None,
    panel_client: RemnawaveClient | None = None,
) -> Node:
    resolved = _resolve_request(request or ProvisionNodeRequest())
    vultr = vultr_client or VultrClient()
    panel = panel_client or RemnawaveClient()
    repo = Repository(session)

    secret_key = await panel.generate_node_secret()
    cloud_init = build_remnawave_node_cloud_init(secret_key, node_port=resolved.node_port)
    instance = await vultr.create_instance(
        region=resolved.region,
        plan=resolved.plan,
        os_id=resolved.os_id,
        label=resolved.name,
        user_data=cloud_init,
        ssh_key_ids=resolved.ssh_key_ids,
        tags=resolved.tags,
        enable_ipv6=resolved.enable_ipv6,
    )

    panel_node: PanelNode | None = None
    panel_hosts: list[PanelHost] = []
    try:
        if not instance.main_ip:
            instance = await vultr.wait_for_main_ip(instance.id)

        panel_node = await panel.create_node(
            name=resolved.name,
            address=instance.main_ip,
            port=resolved.node_port,
            config_profile_uuid=resolved.config_profile_uuid,
            active_inbound_uuids=resolved.active_inbound_uuids,
            is_traffic_tracking_active=settings.REMNAWAVE_NODE_TRAFFIC_TRACKING,
            country_code=resolved.country_code,
            provider_uuid=resolved.provider_uuid,
            tags=resolved.tags,
        )
        panel_hosts = await _create_hosts_for_node(
            panel,
            resolved=resolved,
            panel_node=panel_node,
            address=instance.main_ip,
        )
        return await repo.create_node(
            tier=resolved.tier,
            capacity=resolved.capacity,
            region=resolved.region,
            provider="vultr",
            provider_instance_id=instance.id,
            ip_address=instance.main_ip,
            panel_node_id=panel_node.uuid,
            current_users=0,
            static_ips=[],
            status="disabled" if panel_node.is_disabled else "active",
            name=resolved.name,
        )
    except Exception:
        await session.rollback()
        for host in panel_hosts:
            try:
                await panel.delete_host(host.uuid)
            except Exception:
                logger.exception("Failed to cleanup Remnawave host uuid=%s", host.uuid)
        if panel_node is not None:
            try:
                await panel.delete_node(panel_node.uuid)
            except Exception:
                logger.exception("Failed to cleanup Remnawave node uuid=%s", panel_node.uuid)
        try:
            await vultr.delete_instance(instance.id)
        except Exception:
            logger.exception("Failed to cleanup Vultr instance id=%s", instance.id)
        raise


async def decommission_vultr_node(
    session: AsyncSession,
    node_id: int,
    *,
    vultr_client: VultrClient | None = None,
    panel_client: RemnawaveClient | None = None,
) -> bool:
    repo = Repository(session)
    node = await repo.get_node(node_id)
    if node is None:
        return False

    panel = panel_client or RemnawaveClient()
    vultr = vultr_client or VultrClient()

    if node.panel_node_id:
        await _delete_hosts_for_node(panel, node.panel_node_id)
        await panel.delete_node(node.panel_node_id)
    if node.provider == "vultr" and node.provider_instance_id:
        await vultr.delete_instance(node.provider_instance_id)

    return await repo.delete_node(node.id)


async def ensure_capacity_node(
    session: AsyncSession,
    *,
    tier: str = "premium",
    region: str | None = None,
    provision_request: ProvisionNodeRequest | None = None,
    vultr_client: VultrClient | None = None,
    panel_client: RemnawaveClient | None = None,
) -> Node:
    repo = Repository(session)
    available_nodes = await repo.list_available_nodes(tier=tier, region=region)
    if available_nodes:
        return available_nodes[0]

    request = provision_request or ProvisionNodeRequest(tier=tier, region=region)
    if provision_request is not None:
        updates: dict[str, str] = {}
        if provision_request.tier != tier:
            updates["tier"] = tier
        if region is not None and provision_request.region is None:
            updates["region"] = region
        if updates:
            request = replace(provision_request, **updates)

    return await provision_vultr_node(
        session,
        request,
        vultr_client=vultr_client,
        panel_client=panel_client,
    )


async def assign_subscription_to_node(
    session: AsyncSession,
    subscription_id: int,
    *,
    tier: str = "premium",
    region: str | None = None,
    provision_request: ProvisionNodeRequest | None = None,
    vultr_client: VultrClient | None = None,
    panel_client: RemnawaveClient | None = None,
) -> Node:
    repo = Repository(session)
    subscription = await repo.get_subscription(subscription_id)
    if subscription is None:
        raise AutoscalerError(f"Subscription not found: {subscription_id}")

    for existing_ref in subscription.node_ids or []:
        node = await _get_node_by_ref(repo, str(existing_ref))
        if node is not None:
            return node

    node = await ensure_capacity_node(
        session,
        tier=tier,
        region=region,
        provision_request=provision_request,
        vultr_client=vultr_client,
        panel_client=panel_client,
    )
    updated_node = await repo.update_node(node.id, current_users=node.current_users + 1)
    if updated_node is None:
        raise AutoscalerError(f"Node disappeared while assigning subscription: {node.id}")

    await repo.update_subscription(subscription.id, node_ids=[_node_ref(updated_node)])
    return updated_node


async def move_subscription_to_region(
    session: AsyncSession,
    subscription_id: int,
    region: str,
    *,
    tier: str = "premium",
    provision_request: ProvisionNodeRequest | None = None,
    decommission_empty: bool = True,
    vultr_client: VultrClient | None = None,
    panel_client: RemnawaveClient | None = None,
) -> Node:
    repo = Repository(session)
    subscription = await repo.get_subscription(subscription_id)
    if subscription is None:
        raise AutoscalerError(f"Subscription not found: {subscription_id}")

    current_nodes: list[Node] = []
    seen_node_ids: set[int] = set()
    for node_ref in subscription.node_ids or []:
        node = await _get_node_by_ref(repo, str(node_ref))
        if node is None or node.id in seen_node_ids:
            continue
        seen_node_ids.add(node.id)
        current_nodes.append(node)
        if node.region == region and node.status == "active":
            return node

    target_node = await ensure_capacity_node(
        session,
        tier=tier,
        region=region,
        provision_request=provision_request,
        vultr_client=vultr_client,
        panel_client=panel_client,
    )
    updated_target = await repo.update_node(target_node.id, current_users=target_node.current_users + 1)
    if updated_target is None:
        raise AutoscalerError(f"Node disappeared while moving subscription: {target_node.id}")

    await repo.update_subscription(subscription.id, node_ids=[_node_ref(updated_target)])

    for old_node in current_nodes:
        if old_node.id == updated_target.id:
            continue
        latest_old = await repo.get_node(old_node.id)
        if latest_old is None:
            continue
        updated_old = await repo.update_node(latest_old.id, current_users=max(0, latest_old.current_users - 1))
        if (
            decommission_empty
            and updated_old is not None
            and updated_old.current_users == 0
            and updated_old.provider == "vultr"
        ):
            await decommission_vultr_node(
                session,
                updated_old.id,
                vultr_client=vultr_client,
                panel_client=panel_client,
            )

    return updated_target


async def release_subscription_nodes(
    session: AsyncSession,
    subscription_id: int,
    *,
    decommission_empty: bool = True,
    vultr_client: VultrClient | None = None,
    panel_client: RemnawaveClient | None = None,
) -> list[Node]:
    repo = Repository(session)
    subscription = await repo.get_subscription(subscription_id)
    if subscription is None or not subscription.node_ids:
        return []

    released_nodes: list[Node] = []
    seen_node_ids: set[int] = set()
    for node_ref in subscription.node_ids:
        node = await _get_node_by_ref(repo, str(node_ref))
        if node is None or node.id in seen_node_ids:
            continue
        seen_node_ids.add(node.id)

        updated_node = await repo.update_node(node.id, current_users=max(0, node.current_users - 1))
        if updated_node is None:
            continue
        released_nodes.append(updated_node)

        if decommission_empty and updated_node.current_users == 0 and updated_node.provider == "vultr":
            await decommission_vultr_node(
                session,
                updated_node.id,
                vultr_client=vultr_client,
                panel_client=panel_client,
            )

    await repo.update_subscription(subscription.id, node_ids=[])
    return released_nodes


def _normalize_regions(regions: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for region in regions:
        code = region.strip().lower()
        if code and code not in seen:
            seen.add(code)
            normalized.append(code)
    return normalized


def _country_code_for_region(region: str) -> str | None:
    option = PREMIUM_REGIONS.get(region)
    if option is None:
        return None
    return option.country_code


def _request_for_region(base_request: ProvisionNodeRequest | None, region: str) -> ProvisionNodeRequest:
    country_code = _country_code_for_region(region)
    if base_request is None:
        return ProvisionNodeRequest(region=region, country_code=country_code)
    updates: dict[str, str] = {"region": region}
    if country_code is not None:
        updates["country_code"] = country_code
    return replace(base_request, **updates)


async def autoscale_premium_pool(
    session: AsyncSession,
    *,
    regions: list[str] | tuple[str, ...],
    min_free_slots: int = 1,
    min_active_nodes: int = 0,
    max_provisions_per_region: int = 1,
    decommission_empty: bool = True,
    provision_request: ProvisionNodeRequest | None = None,
    vultr_client: VultrClient | None = None,
    panel_client: RemnawaveClient | None = None,
) -> AutoscalePoolResult:
    if min_free_slots < 0:
        raise AutoscalerError("min_free_slots must be non-negative")
    if min_active_nodes < 0:
        raise AutoscalerError("min_active_nodes must be non-negative")
    if max_provisions_per_region < 0:
        raise AutoscalerError("max_provisions_per_region must be non-negative")

    normalized_regions = _normalize_regions(regions)
    result = AutoscalePoolResult(checked_regions=len(normalized_regions))
    repo = Repository(session)

    for region in normalized_regions:
        provisions_for_region = 0
        while provisions_for_region < max_provisions_per_region:
            nodes = await repo.list_nodes(tier="premium", region=region, provider="vultr", status="active")
            free_slots = sum(max(0, node.capacity - node.current_users) for node in nodes)
            if len(nodes) >= min_active_nodes and free_slots >= min_free_slots:
                break

            node = await provision_vultr_node(
                session,
                _request_for_region(provision_request, region),
                vultr_client=vultr_client,
                panel_client=panel_client,
            )
            result.provisioned_node_ids.append(node.id)
            provisions_for_region += 1

    if not decommission_empty:
        return result

    configured_regions = set(normalized_regions)
    active_nodes = await repo.list_nodes(tier="premium", provider="vultr", status="active")
    regions_with_nodes = sorted({node.region for node in active_nodes})
    for region in regions_with_nodes:
        region_nodes = [node for node in active_nodes if node.region == region]
        non_empty_nodes = [node for node in region_nodes if node.current_users > 0]
        empty_nodes = sorted(
            [node for node in region_nodes if node.current_users == 0],
            key=lambda item: item.id,
        )

        kept_active_count = len(non_empty_nodes)
        kept_free_slots = sum(max(0, node.capacity - node.current_users) for node in non_empty_nodes)
        keep_empty_ids: set[int] = set()
        for node in empty_nodes:
            if (
                region in configured_regions
                and (kept_active_count < min_active_nodes or kept_free_slots < min_free_slots)
            ):
                keep_empty_ids.add(node.id)
                kept_active_count += 1
                kept_free_slots += max(0, node.capacity - node.current_users)

        for node in empty_nodes:
            if node.id in keep_empty_ids:
                continue
            deleted = await decommission_vultr_node(
                session,
                node.id,
                vultr_client=vultr_client,
                panel_client=panel_client,
            )
            if deleted:
                result.decommissioned_node_ids.append(node.id)

    return result
