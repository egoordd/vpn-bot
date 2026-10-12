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
        texts.WELCOME, texts.ISSUED, texts.ALREADY, texts.PICK_DEVICE, texts.help_text(1), texts.ERROR,
        texts.steps("iPhone", core.sub_link("T")), texts.status(access, core.sub_link("T")),
    ]
    for text in rendered:
        assert "unlock" not in text.lower(), text
        assert "анлок" not in text.lower(), text


def test_status_shows_expired_access():
    access = core.Access("corp_mrt_1", "T", int(time.time()) - 60, "active", 0, 10 * 1024**3)
    assert not access.active
    assert "закончилась" in texts.status(access, "L")


def _all_keyboards():
    from marat_bot import keyboards as kb

    active = core.Access("corp_mrt_1", "T", int(time.time()) + 3600, "active", 0, 10 * 1024**3)
    expired = core.Access("corp_mrt_1", "T", int(time.time()) - 60, "active", 0, 10 * 1024**3)
    return [
        kb.main(None), kb.main(active), kb.main(expired), kb.my_subscription(), kb.tariffs(),
        kb.checkout(), kb.devices(), kb.device_steps("https://a.example", "https://b.example"),
        kb.help_menu(), kb.back(),
    ]


def test_every_button_has_a_handler():
    from marat_bot import app, keyboards as kb

    for markup in _all_keyboards():
        for data in kb.callbacks(markup):
            assert data in app.HANDLED or data.startswith(app.HANDLED_PREFIXES), data


def test_every_stub_has_a_message():
    from marat_bot import app, keyboards as kb

    stubs = {d.split(":", 1)[1] for m in _all_keyboards() for d in kb.callbacks(m) if d.startswith("stub:")}
    assert stubs <= set(app.STUBS), stubs - set(app.STUBS)


def test_plans_and_new_screens_stay_unbranded():
    assert core.PLANS and all(price > 0 for _, _, price in core.PLANS)
    for text in (texts.tariffs(), texts.checkout("1 месяц", 199), texts.referral("https://t.me/x"),
                 texts.help_text(1), texts.HOW_IT_WORKS, texts.home(None)):
        assert "unlock" not in text.lower()


class _FakeTg:
    def __init__(self):
        self.sent, self.edits, self.answers = [], [], []

    async def send(self, chat, text, markup=None):
        self.sent.append((chat, text, markup))

    async def edit(self, chat, msg, text, markup=None):
        self.edits.append((chat, msg, text, markup))

    async def answer(self, callback_id, text=None, alert=False):
        self.answers.append((callback_id, text, alert))


def _call(data, user=5):
    return {"id": "cb", "data": data, "from": {"id": user}, "message": {"chat": {"id": user}, "message_id": 7}}


def test_screens_answer_without_panel_for_a_new_user(monkeypatch, tmp_path):
    import asyncio
    from marat_bot import app

    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    tg = _FakeTg()

    async def run():
        await app.on_message(tg, {"text": "/start", "chat": {"id": 5}, "from": {"id": 5}})
        for data in ("tariffs", "plan:30", "help", "how", "stub:pay", "stub:support", "connect"):
            await app.on_callback(tg, _call(data))

    asyncio.run(run())
    assert "Марат VPN" in tg.sent[0][1]
    edited = [e[2] for e in tg.edits]
    assert any("Тарифы" in t for t in edited) and any("Оплата" in t for t in edited)
    alerts = [a[1] for a in tg.answers if a[2]]
    assert any("Оплата скоро" in a for a in alerts)
    assert texts.NEED_ACCESS in alerts
    app._store.cache_clear()
