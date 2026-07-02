import pytest

from config import Settings, settings


def make_settings(**overrides):
    values = {
        "BOT_TOKEN": "secret-token",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/0",
        "WG_SERVER_PUBLIC_KEY": "server-key",
        "WG_SERVER_ENDPOINT": "127.0.0.1:51821",
        "ADMIN_IDS": "",
        "SUPPORT_USERNAME": "support",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,2,3", [1, 2, 3]),
        ("[1, 2]", [1, 2]),
        ("", []),
        (" 1 , 2 ", [1, 2]),
    ],
)
def test_admin_ids_list(raw, expected):
    assert make_settings(ADMIN_IDS=raw).admin_ids_list == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([1, 2], "1,2"),
        (None, ""),
        (5, "5"),
    ],
)
def test_parse_admin_ids_validator(raw, expected):
    assert Settings.parse_admin_ids(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("bot_username", "manual", "expected"),
    [
        ("supportbot", "", "@supportbot"),        # prefers the real support-relay bot
        ("supportbot", "manual", "@supportbot"),  # relay bot wins over a manual @username
        ("", "foo", "@foo"),                      # falls back to the manual username
        ("", "@foo", "@foo"),
        ("", "", "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d"),
    ],
)
def test_support_contact(bot_username, manual, expected):
    settings = make_settings(SUPPORT_BOT_USERNAME=bot_username, SUPPORT_USERNAME=manual)
    assert settings.support_contact == expected


@pytest.mark.unit
def test_bot_token_returns_secret_value():
    assert make_settings(BOT_TOKEN="test-secret").bot_token == "test-secret"
    assert settings.bot_token == "test:token"


@pytest.mark.unit
def test_autoscaler_list_settings_are_parsed():
    parsed = make_settings(
        VULTR_SSH_KEY_IDS="key-1, key-2",
        REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS="squad-1, squad-2",
        REMNAWAVE_NODE_INBOUND_UUIDS="inbound-1, inbound-2",
        VULTR_API_TOKEN="vultr-secret",
        AUTOSCALE_PREMIUM_REGIONS="ams, fra",
        PANEL_PROVIDER="marzban",
        MARZBAN_ACCESS_TOKEN="marzban-token",
        MARZBAN_PASSWORD="marzban-password",
        MARZBAN_DEFAULT_PROXIES='{"vless":{}}',
        MARZBAN_DEFAULT_INBOUNDS='{"vless":["VLESS TCP REALITY"]}',
    )

    assert parsed.PANEL_PROVIDER == "marzban"
    assert parsed.vultr_ssh_key_ids_list == ["key-1", "key-2"]
    assert parsed.remnawave_default_internal_squad_uuids_list == ["squad-1", "squad-2"]
    assert parsed.remnawave_node_inbound_uuids_list == ["inbound-1", "inbound-2"]
    assert parsed.vultr_api_token == "vultr-secret"
    assert parsed.autoscale_premium_regions_list == ["ams", "fra"]
    assert parsed.marzban_access_token == "marzban-token"
    assert parsed.marzban_password == "marzban-password"
    assert parsed.marzban_default_proxies_dict == {"vless": {}}
    assert parsed.marzban_default_inbounds_dict == {"vless": ["VLESS TCP REALITY"]}


@pytest.mark.unit
def test_marzban_json_settings_must_be_objects():
    with pytest.raises(ValueError, match="MARZBAN_DEFAULT_PROXIES"):
        make_settings(MARZBAN_DEFAULT_PROXIES="[]").marzban_default_proxies_dict
