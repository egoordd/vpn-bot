import base64
import json

import pytest

from database.repository import Repository
from services import awg_provision
from services.awg_keys import generate_keypair, public_key_for
from services.awg_provision import (
    AwgClientConfig,
    _build_config,
    _node_client_ip,
    ensure_client_configs,
)

US_NODE = {
    "flag": "🇺🇸",
    "name": "США",
    "ssh_host": "144.172.101.217",
    "ssh_user": "root",
    "endpoint": "144.172.101.217:51820",
    "server_pubkey": "tpTvM9Vk7yz8u/f3whF66AcJKgvGXTXFX2zp1GzUMyU=",
    "subnet": "10.13.13.0/24",
}
NL_NODE = {
    "flag": "🇳🇱",
    "name": "Нидерланды",
    "ssh_host": "107.189.22.160",
    "ssh_user": "root",
    "endpoint": "107.189.22.160:51820",
    "server_pubkey": "ZaHOMPke/MfJTBVcwqUCg80qIGcMJ+dtCv7FfhGcXnU=",
    "subnet": "10.13.14.0/24",
}


def test_generate_keypair_returns_valid_32_byte_keys():
    private_key, public_key = generate_keypair()
    assert len(base64.b64decode(private_key)) == 32
    assert len(base64.b64decode(public_key)) == 32
    assert private_key != public_key


def test_public_key_for_is_deterministic_and_matches_generation():
    private_key, public_key = generate_keypair()
    assert public_key_for(private_key) == public_key


def test_node_client_ip_maps_index_into_subnet():
    assert _node_client_ip("10.13.13.0/24", 2) == "10.13.13.2"
    assert _node_client_ip("10.13.14.0/24", 5) == "10.13.14.5"


def test_build_config_contains_peer_and_obfuscation_params():
    config = _build_config(US_NODE, "PRIVKEYAAA=", "10.13.13.7")
    assert "PrivateKey = PRIVKEYAAA=" in config
    assert "Address = 10.13.13.7/32" in config
    assert f"PublicKey = {US_NODE['server_pubkey']}" in config
    assert "Endpoint = 144.172.101.217:51820" in config
    assert "Jc = 4" in config
    assert "H4 = 4567890" in config
    assert "AllowedIPs = 0.0.0.0/0, ::/0" in config


@pytest.mark.integration
async def test_ensure_client_configs_provisions_all_nodes(db_session, monkeypatch):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=555, username="awg")

    monkeypatch.setattr(
        "services.awg_provision.settings.AWG_NODES",
        json.dumps({"us": US_NODE, "nl": NL_NODE}),
    )
    calls: list[tuple[str, str]] = []

    async def fake_set_peer(node, public_key, client_ip):
        calls.append((node["ssh_host"], client_ip))

    monkeypatch.setattr(awg_provision, "_set_peer", fake_set_peer)

    configs = await ensure_client_configs(db_session, user.id)

    assert [c.node_code for c in configs] == ["us", "nl"]
    assert all(isinstance(c, AwgClientConfig) for c in configs)
    # index starts at 2 -> same host octet on both nodes
    assert ("144.172.101.217", "10.13.13.2") in calls
    assert ("107.189.22.160", "10.13.14.2") in calls

    stored = await repo.get_amneziawg_client_by_user_id(user.id)
    assert stored is not None
    assert public_key_for(stored.private_key) == stored.public_key


@pytest.mark.integration
async def test_ensure_client_configs_is_idempotent(db_session, monkeypatch):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=556, username="awg2")
    monkeypatch.setattr(
        "services.awg_provision.settings.AWG_NODES", json.dumps({"us": US_NODE})
    )

    async def fake_set_peer(node, public_key, client_ip):
        return None

    monkeypatch.setattr(awg_provision, "_set_peer", fake_set_peer)

    first = await ensure_client_configs(db_session, user.id)
    second = await ensure_client_configs(db_session, user.id)

    # same identity reused, not a new keypair
    assert first[0].config_text == second[0].config_text
    client = await repo.get_amneziawg_client_by_user_id(user.id)
    assert client.ip_index == 2


@pytest.mark.integration
async def test_ensure_client_configs_empty_when_no_nodes(db_session, monkeypatch):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=557, username="awg3")
    monkeypatch.setattr("services.awg_provision.settings.AWG_NODES", "{}")
    assert await ensure_client_configs(db_session, user.id) == []
