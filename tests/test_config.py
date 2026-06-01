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
    ("raw", "expected"),
    [
        ("foo", "@foo"),
        ("@foo", "@foo"),
        ("", "\u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d"),
    ],
)
def test_support_contact(raw, expected):
    assert make_settings(SUPPORT_USERNAME=raw).support_contact == expected


@pytest.mark.unit
def test_bot_token_returns_secret_value():
    assert make_settings(BOT_TOKEN="test-secret").bot_token == "test-secret"
    assert settings.bot_token == "test:token"
