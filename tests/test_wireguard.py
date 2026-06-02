import os
import stat
from datetime import datetime, timezone
from unittest.mock import AsyncMock, call

import pytest

from database.repository import Repository
from services import wireguard
from services.wireguard import WireGuardError


@pytest.fixture
def wg_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(wireguard.settings, "WG_CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(wireguard.settings, "WG_INTERFACE", "awg-test")
    monkeypatch.setattr(wireguard.settings, "WG_SERVER_PUBLIC_KEY", "SERVERPUB=")
    monkeypatch.setattr(wireguard.settings, "WG_SERVER_ENDPOINT", "127.0.0.1:51821")
    monkeypatch.setattr(wireguard.settings, "WG_CLIENT_DNS", "9.9.9.9")
    monkeypatch.setattr(wireguard.settings, "WG_ALLOWED_IPS", "0.0.0.0/0")
    monkeypatch.setattr(wireguard.settings, "WG_CLIENT_ADDRESS_POOL", "10.9.0.0/24")
    monkeypatch.setattr(wireguard.settings, "AWG_JC", 4)
    monkeypatch.setattr(wireguard.settings, "AWG_JMIN", 40)
    monkeypatch.setattr(wireguard.settings, "AWG_JMAX", 70)
    monkeypatch.setattr(wireguard.settings, "AWG_S1", 50)
    monkeypatch.setattr(wireguard.settings, "AWG_S2", 100)
    monkeypatch.setattr(wireguard.settings, "AWG_H1", 1234567)
    monkeypatch.setattr(wireguard.settings, "AWG_H2", 2345678)
    monkeypatch.setattr(wireguard.settings, "AWG_H3", 3456789)
    monkeypatch.setattr(wireguard.settings, "AWG_H4", 4567890)
    return tmp_path


@pytest.mark.unit
async def test_create_client_config_obfuscation_order(wg_settings):
    path, text = await wireguard.create_client_config(
        user_id=55,
        public_key="CLIENTPUB=",
        private_key="CLIENTPRIV=",
        ip="10.9.0.2",
    )

    assert path.endswith("client_55.conf")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert "[Interface]" in text
    assert "Address = 10.9.0.2/32" in text
    assert "DNS = 9.9.9.9" in text
    assert "MTU" not in text
    assert "[Peer]" in text
    assert "PublicKey = SERVERPUB=" in text
    assert "Endpoint = 127.0.0.1:51821" in text
    assert "AllowedIPs = 0.0.0.0/0" in text
    assert "PersistentKeepalive = 25" in text

    lines = text.splitlines()
    expected_obfuscation = [
        "Jc = 4",
        "Jmin = 40",
        "Jmax = 70",
        "S1 = 50",
        "S2 = 100",
        "H1 = 1234567",
        "H2 = 2345678",
        "H3 = 3456789",
        "H4 = 4567890",
    ]
    dns_index = lines.index("DNS = 9.9.9.9")
    assert lines[dns_index + 1 : dns_index + 1 + len(expected_obfuscation)] == expected_obfuscation
    assert lines[dns_index + 1 + len(expected_obfuscation)] == ""
    assert lines.index("[Interface]") < dns_index < lines.index("[Peer]")
    for line in expected_obfuscation:
        assert lines.index("[Interface]") < lines.index(line) < lines.index("[Peer]")


@pytest.mark.unit
async def test_create_client_config_requires_server_public_key(wg_settings, monkeypatch):
    monkeypatch.setattr(wireguard.settings, "WG_SERVER_PUBLIC_KEY", "")
    with pytest.raises(WireGuardError):
        await wireguard.create_client_config(1, "pub", "priv", "10.9.0.2")


@pytest.mark.unit
async def test_create_client_config_requires_server_endpoint(wg_settings, monkeypatch):
    monkeypatch.setattr(wireguard.settings, "WG_SERVER_ENDPOINT", "")
    with pytest.raises(WireGuardError):
        await wireguard.create_client_config(1, "pub", "priv", "10.9.0.2")


@pytest.mark.unit
async def test_generate_keypair(monkeypatch):
    run = AsyncMock(side_effect=["PRIV", "PUB"])
    monkeypatch.setattr(wireguard, "_run_command", run)

    assert await wireguard.generate_keypair() == ("PRIV", "PUB")
    run.assert_has_awaits(
        [
            call(["awg", "genkey"]),
            call(["awg", "pubkey"], input_text="PRIV\n"),
        ]
    )


@pytest.mark.unit
async def test_add_peer_and_remove_peer(wg_settings, monkeypatch):
    run = AsyncMock(return_value="")
    monkeypatch.setattr(wireguard, "_run_command", run)

    await wireguard.add_peer("PUB", "10.9.0.2/32")
    await wireguard.remove_peer("PUB")

    run.assert_has_awaits(
        [
            call(["awg", "set", "awg-test", "peer", "PUB", "allowed-ips", "10.9.0.2/32"]),
            call(["awg", "set", "awg-test", "peer", "PUB", "remove"]),
        ]
    )


@pytest.mark.integration
async def test_allocate_next_ip_skips_gateway(wg_settings, db_session):
    assert await wireguard.allocate_next_ip(db_session) == "10.9.0.2"


@pytest.mark.integration
async def test_allocate_next_ip_exhausted(wg_settings, db_session, monkeypatch):
    monkeypatch.setattr(wireguard.settings, "WG_CLIENT_ADDRESS_POOL", "10.9.0.0/30")
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=10)
    await repo.create_wireguard_key(user.id, "PUB", "PRIV", "10.9.0.2", "/tmp/client.conf")

    with pytest.raises(WireGuardError):
        await wireguard.allocate_next_ip(db_session)


@pytest.mark.integration
async def test_rotate_user_key_updates_existing_key_in_place(wg_settings, db_session, monkeypatch):
    run = AsyncMock(side_effect=["", "NEWPRIV", "NEWPUB", ""])
    monkeypatch.setattr(wireguard, "_run_command", run)
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=11)
    existing = await repo.create_wireguard_key(user.id, "OLDPUB", "OLDPRIV", "10.9.0.9", "/old.conf")

    key, config_text = await wireguard.rotate_user_key(db_session, user.id)
    keys = await repo.get_all_wireguard_keys()

    assert key.id == existing.id
    assert key.public_key == "NEWPUB"
    assert key.private_key == "NEWPRIV"
    assert key.ip_address == "10.9.0.9"
    assert len(keys) == 1
    assert "PrivateKey = NEWPRIV" in config_text
    assert "Address = 10.9.0.9/32" in config_text
    run.assert_has_awaits(
        [
            call(["awg", "set", "awg-test", "peer", "OLDPUB", "remove"]),
            call(["awg", "genkey"]),
            call(["awg", "pubkey"], input_text="NEWPRIV\n"),
            call(["awg", "set", "awg-test", "peer", "NEWPUB", "allowed-ips", "10.9.0.9/32"]),
        ]
    )


@pytest.mark.integration
async def test_rotate_user_key_creates_key_when_missing(wg_settings, db_session, monkeypatch):
    run = AsyncMock(side_effect=["PRIV", "PUB", ""])
    monkeypatch.setattr(wireguard, "_run_command", run)
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=12)

    key, config_text = await wireguard.rotate_user_key(db_session, user.id)

    assert key.public_key == "PUB"
    assert key.private_key == "PRIV"
    assert key.ip_address == "10.9.0.2"
    assert (await repo.get_wireguard_key_by_user_id(user.id)).id == key.id
    assert "Address = 10.9.0.2/32" in config_text


@pytest.mark.integration
async def test_resync_all_peers_counts_successes(wg_settings, db_session, monkeypatch):
    repo = Repository(db_session)
    user1 = await repo.create_user(telegram_id=13)
    user2 = await repo.create_user(telegram_id=14)
    await repo.create_wireguard_key(user1.id, "PUB1", "PRIV1", "10.9.0.2", "/one.conf")
    await repo.create_wireguard_key(user2.id, "PUB2", "PRIV2", "10.9.0.3", "/two.conf")
    add_peer = AsyncMock(side_effect=[None, WireGuardError("boom")])
    monkeypatch.setattr(wireguard, "add_peer", add_peer)

    assert await wireguard.resync_all_peers(db_session) == 1
    add_peer.assert_has_awaits([call("PUB1", "10.9.0.2/32"), call("PUB2", "10.9.0.3/32")])


@pytest.mark.integration
async def test_ensure_user_peer_rebuilds_existing_key(wg_settings, db_session, monkeypatch):
    run = AsyncMock(return_value="")
    monkeypatch.setattr(wireguard, "_run_command", run)
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=15)
    key = await repo.create_wireguard_key(user.id, "PUB", "PRIV", "10.9.0.2", "/old.conf")

    returned_key, config_text = await wireguard.ensure_user_peer(db_session, user.id)

    assert returned_key.id == key.id
    assert "PrivateKey = PRIV" in config_text
    run.assert_awaited_once_with(["awg", "set", "awg-test", "peer", "PUB", "allowed-ips", "10.9.0.2/32"])


@pytest.mark.integration
async def test_ensure_user_peer_creates_key_when_missing(wg_settings, db_session, monkeypatch):
    run = AsyncMock(side_effect=["PRIV", "PUB", ""])
    monkeypatch.setattr(wireguard, "_run_command", run)
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=16)

    key, config_text = await wireguard.ensure_user_peer(db_session, user.id)

    assert key.public_key == "PUB"
    assert key.ip_address == "10.9.0.2"
    assert "PrivateKey = PRIV" in config_text


@pytest.mark.unit
async def test_get_client_config_text_helpers(wg_settings):
    config_path, config_text = await wireguard.create_client_config(99, "PUB", "PRIV", "10.9.0.2")

    assert await wireguard.get_client_config_text(99) == config_text
    assert await wireguard.get_client_config_text_by_path(config_path) == config_text


@pytest.mark.unit
async def test_get_client_config_text_missing_raises(wg_settings):
    with pytest.raises(WireGuardError):
        await wireguard.get_client_config_text(404)
