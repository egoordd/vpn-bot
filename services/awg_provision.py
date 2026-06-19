"""AmneziaWG per-user provisioning across nodes (SSH-based).

Each user gets ONE AmneziaWG keypair, registered as a peer on every node in
``settings.awg_nodes_dict``. Unlike VLESS (panel-managed) and Hysteria2 (shared
password), WireGuard is per-peer: the server must know each client's public key,
so we SSH into every node and run ``awg set ... peer`` + ``awg-quick save`` (the
save persists the peer into awg0.conf so it survives a reboot).

The same keypair is reused on all nodes; the shared ``ip_index`` maps to a
per-node tunnel IP (node subnet network address + index).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.repository import Repository
from services.awg_keys import generate_keypair

logger = logging.getLogger(__name__)

_SSH_TIMEOUT = 35


class AwgProvisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AwgClientConfig:
    node_code: str
    flag: str
    name: str
    config_text: str


def _node_client_ip(subnet: str, ip_index: int) -> str:
    network = ipaddress.ip_network(subnet, strict=False)
    return str(network.network_address + ip_index)


def _build_config(node: dict[str, str], private_key: str, client_ip: str) -> str:
    return "\n".join(
        [
            "[Interface]",
            f"PrivateKey = {private_key}",
            f"Address = {client_ip}/32",
            f"DNS = {settings.WG_CLIENT_DNS}",
            f"Jc = {settings.AWG_JC}",
            f"Jmin = {settings.AWG_JMIN}",
            f"Jmax = {settings.AWG_JMAX}",
            f"S1 = {settings.AWG_S1}",
            f"S2 = {settings.AWG_S2}",
            f"H1 = {settings.AWG_H1}",
            f"H2 = {settings.AWG_H2}",
            f"H3 = {settings.AWG_H3}",
            f"H4 = {settings.AWG_H4}",
            "",
            "[Peer]",
            f"PublicKey = {node['server_pubkey']}",
            f"Endpoint = {node['endpoint']}",
            "AllowedIPs = 0.0.0.0/0, ::/0",
            "PersistentKeepalive = 25",
            "",
        ]
    )


async def _ssh(node: dict[str, str], remote_command: str) -> None:
    host = node["ssh_host"]
    user = node.get("ssh_user", "root")
    argv = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if settings.AWG_SSH_KEY:
        argv += ["-i", settings.AWG_SSH_KEY, "-o", "IdentitiesOnly=yes"]
    argv += [f"{user}@{host}", remote_command]
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=_SSH_TIMEOUT)
    except (FileNotFoundError, asyncio.TimeoutError) as exc:
        raise AwgProvisionError(f"SSH to {host} failed: {exc}") from exc
    if process.returncode != 0:
        detail = stderr.decode().strip() or stdout.decode().strip()
        raise AwgProvisionError(f"SSH to {host} returned {process.returncode}: {detail}")


async def _set_peer(node: dict[str, str], public_key: str, client_ip: str) -> None:
    command = (
        f"awg set awg0 peer '{public_key}' allowed-ips {client_ip}/32 "
        f"&& awg-quick save awg0"
    )
    await _ssh(node, command)


async def _remove_peer(node: dict[str, str], public_key: str) -> None:
    command = f"awg set awg0 peer '{public_key}' remove && awg-quick save awg0"
    await _ssh(node, command)


async def ensure_client_configs(session: AsyncSession, user_id: int) -> list[AwgClientConfig]:
    """Provision (idempotently) the user on every AWG node and return per-node configs."""
    nodes = settings.awg_nodes_dict
    if not nodes:
        return []

    repo = Repository(session)
    client = await repo.get_amneziawg_client_by_user_id(user_id)
    if client is None:
        private_key, public_key = generate_keypair()
        ip_index = await repo.next_amneziawg_ip_index()
        client = await repo.create_amneziawg_client(
            user_id=user_id,
            public_key=public_key,
            private_key=private_key,
            ip_index=ip_index,
        )

    async def _provision(code: str, node: dict[str, str]) -> AwgClientConfig:
        client_ip = _node_client_ip(node["subnet"], client.ip_index)
        await _set_peer(node, client.public_key, client_ip)
        return AwgClientConfig(
            node_code=code,
            flag=node.get("flag", ""),
            name=node.get("name", code),
            config_text=_build_config(node, client.private_key, client_ip),
        )

    # Provision every node concurrently; a slow/failing node doesn't block the
    # others. The keypair is shared, so a later retry fills in any missing node.
    results = await asyncio.gather(
        *(_provision(code, node) for code, node in nodes.items()),
        return_exceptions=True,
    )
    configs: list[AwgClientConfig] = []
    for result in results:
        if isinstance(result, AwgClientConfig):
            configs.append(result)
        elif isinstance(result, Exception):
            logger.warning("AmneziaWG provisioning failed for a node (user_id=%s): %s", user_id, result)
    logger.info("Provisioned AmneziaWG for user_id=%s on %d/%d node(s)", user_id, len(configs), len(nodes))
    return configs


async def remove_client(session: AsyncSession, user_id: int) -> None:
    """Revoke the user's peer on every node and drop the DB row."""
    repo = Repository(session)
    client = await repo.get_amneziawg_client_by_user_id(user_id)
    if client is None:
        return
    for node in settings.awg_nodes_dict.values():
        try:
            await _remove_peer(node, client.public_key)
        except AwgProvisionError:
            logger.warning("Failed to remove AWG peer on %s for user_id=%s", node.get("ssh_host"), user_id)
    await repo.delete_amneziawg_client_by_user_id(user_id)
