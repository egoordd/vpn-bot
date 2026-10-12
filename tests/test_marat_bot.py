"""«Марат VPN»: имена учёток, ссылки, сроки и тексты без упоминаний основного проекта."""
import time

from marat_bot import core, texts


def test_panel_username_fits_the_gateway_pattern():
    import re

    name = core.panel_username(8988612696)
    assert name == "corp_mrt_8988612696"
    assert re.fullmatch(r"(corp|exp|ind)_[a-z0-9_]{1,24}", name)


def test_token_is_taken_from_a_panel_link():
    assert core.token_from_url("https://panel.example/sub/abc123DEF/") == "abc123DEF"
    assert core.token_from_url("https://panel.example/sub/abc/info") == "abc"
    assert core.token_from_url("https://panel.example/user") is None
    assert core.token_from_url(None) is None


def test_links_use_the_neutral_base():
    assert core.sub_link("T") == f"{core.SUB_BASE}/sub/T"
    assert core.happ_link("T") == f"{core.SUB_BASE}/happ/T"
    assert "unlock" not in core.SUB_BASE.lower()


def test_trial_lasts_the_configured_days():
    now = 1_800_000_000
    assert core.trial_expire(now) == now + core.TRIAL_DAYS * 86400


def test_store_remembers_one_trial_per_account(tmp_path):
    store = core.Store(str(tmp_path / "users.sqlite3"))
    assert store.get(1) is None
    store.add(1, "corp_mrt_1")
    store.add(1, "corp_mrt_other")
    assert store.get(1) == "corp_mrt_1"
    assert store.count() == 1


def test_no_text_mentions_the_main_project():
    access = core.Access("corp_mrt_1", "T", int(time.time()) + 3600, "active", 1024**3, 10 * 1024**3)
    rendered = [
        texts.WELCOME, texts.ISSUED, texts.ALREADY, texts.PICK_DEVICE, texts.HELP, texts.ERROR,
        texts.steps("iPhone", core.sub_link("T")), texts.status(access, core.sub_link("T")),
    ]
    for text in rendered:
        assert "unlock" not in text.lower(), text
        assert "анлок" not in text.lower(), text


def test_status_shows_expired_access():
    access = core.Access("corp_mrt_1", "T", int(time.time()) - 60, "active", 0, 10 * 1024**3)
    assert not access.active
    assert "закончился" in texts.status(access, "L")
