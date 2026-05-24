from __future__ import annotations

import asyncio
import ipaddress
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import WireguardKey
from database.repository import Repository

logger = logging.getLogger(__name__)


class WireGuardError(RuntimeError):
    pass


async def _run_command(command: list[str], input_text: str | None = None) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise WireGuardError("wireguard-tools не установлен или команда wg недоступна") from exc

    stdout, stderr = await process.communicate(input_text.encode() if input_text is not None else None)
    if process.returncode != 0:
        error_text = stderr.decode().strip() or stdout.decode().strip()
        raise WireGuardError(f"Ошибка WireGuard CLI: {error_text}")
    return stdout.decode().strip()


async def generate_keypair() -> tuple[str, str]:
    private_key = await _run_command(["wg", "genkey"])
    public_key = await _run_command(["wg", "pubkey"], input_text=f"{private_key}\n")
    return private_key, public_key


def _client_config_path(user_id: int) -> Path:
    return Path(settings.WG_CONFIG_PATH) / f"client_{user_id}.conf"


async def create_client_config(
    user_id: int,
    public_key: str,
    private_key: str,
    ip: str,
) -> tuple[str, str]:
    if not settings.WG_SERVER_PUBLIC_KEY:
        raise WireGuardError("WG_SERVER_PUBLIC_KEY не задан")
    if not settings.WG_SERVER_ENDPOINT:
        raise WireGuardError("WG_SERVER_ENDPOINT не задан")

    config_text = "\n".join(
        [
            "[Interface]",
            f"PrivateKey = {private_key}",
            f"Address = {ip}/32",
            f"DNS = {settings.WG_CLIENT_DNS}",
            "",
            "[Peer]",
            f"PublicKey = {settings.WG_SERVER_PUBLIC_KEY}",
            f"Endpoint = {settings.WG_SERVER_ENDPOINT}",
            f"AllowedIPs = {settings.WG_ALLOWED_IPS}",
            "PersistentKeepalive = 25",
            "",
        ]
    )

    path = _client_config_path(user_id)
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, config_text, "utf-8")
    logger.info("Created WireGuard client config for user_id=%s public_key=%s", user_id, public_key)
    return str(path), config_text


async def add_peer(public_key: str, allowed_ips: str) -> None:
    await _run_command(
        [
            "wg",
            "set",
            settings.WG_INTERFACE,
            "peer",
            public_key,
            "allowed-ips",
            allowed_ips,
        ]
    )
    logger.info("Added WireGuard peer %s with allowed_ips=%s", public_key, allowed_ips)


async def remove_peer(public_key: str) -> None:
    await _run_command(["wg", "set", settings.WG_INTERFACE, "peer", public_key, "remove"])
    logger.info("Removed WireGuard peer %s", public_key)


async def get_client_config_text(user_id: int) -> str:
    path = _client_config_path(user_id)
    if not path.exists():
        raise WireGuardError(f"Конфиг WireGuard не найден: {path}")
    return await asyncio.to_thread(path.read_text, "utf-8")


async def get_client_config_text_by_path(path: str) -> str:
    config_path = Path(path)
    if not config_path.exists():
        raise WireGuardError(f"Конфиг WireGuard не найден: {config_path}")
    return await asyncio.to_thread(config_path.read_text, "utf-8")


async def allocate_next_ip(session: AsyncSession) -> str:
    repo = Repository(session)
    used_ips = await repo.get_used_wireguard_ips()
    network = ipaddress.ip_network(settings.WG_CLIENT_ADDRESS_POOL, strict=False)
    hosts = list(network.hosts())
    for host in hosts[1:]:
        ip = str(host)
        if ip not in used_ips:
            return ip
    raise WireGuardError(f"Свободные IP в пуле {settings.WG_CLIENT_ADDRESS_POOL} закончились")


async def ensure_user_peer(session: AsyncSession, user_id: int) -> tuple[WireguardKey, str]:
    repo = Repository(session)
    existing_key = await repo.get_wireguard_key_by_user_id(user_id)
    if existing_key is not None:
        config_path = Path(existing_key.config_file_path)
        if config_path.exists():
            config_text = await get_client_config_text_by_path(existing_key.config_file_path)
        else:
            config_path_text, config_text = await create_client_config(
                user_id=user_id,
                public_key=existing_key.public_key,
                private_key=existing_key.private_key,
                ip=existing_key.ip_address,
            )
            await repo.update_wireguard_key(existing_key.id, config_file_path=config_path_text)
        await add_peer(existing_key.public_key, f"{existing_key.ip_address}/32")
        return existing_key, config_text

    private_key, public_key = await generate_keypair()
    ip_address = await allocate_next_ip(session)
    config_file_path, config_text = await create_client_config(
        user_id=user_id,
        public_key=public_key,
        private_key=private_key,
        ip=ip_address,
    )
    await add_peer(public_key, f"{ip_address}/32")
    key = await repo.create_wireguard_key(
        user_id=user_id,
        public_key=public_key,
        private_key=private_key,
        ip_address=ip_address,
        config_file_path=config_file_path,
    )
    return key, config_text
