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
        texts.welcome("Марат"), texts.issued("1 января"), texts.ALREADY, texts.PICK_DEVICE, texts.help_text(1),
        texts.ERROR, texts.steps("iPhone / iPad", core.sub_link("T")), texts.status(access, core.sub_link("T")),
        texts.home(access), texts.DESCRIPTION, texts.SHORT_DESCRIPTION,
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
        kb.main(None), kb.main(active), kb.main(expired), kb.main(active, admin=True), kb.my_subscription(), kb.tariffs(),
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

    async def send(self, chat, text, markup=None, effect=None):
        self.sent.append((chat, text, markup))
        self.effects = [*getattr(self, "effects", []), effect]

    async def call(self, method, **params):
        self.calls = [*getattr(self, "calls", []), (method, params)]

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


# --- 12.10.2026: оформление и команды ---

def _rendered_texts():
    now = int(time.time())
    active = core.Access("corp_mrt_1", "T", now + 2 * 86400 + 5 * 3600, "active", 3 * 1024**3, 10 * 1024**3)
    expired = core.Access("corp_mrt_1", "T", now - 60, "active", 10 * 1024**3, 10 * 1024**3)
    return [
        texts.welcome("<Марат & Ко>"), texts.welcome(None), texts.issued("15 октября, 12:00 МСК"), texts.PICK_DEVICE,
        texts.steps("Android", "https://x/sub/T"), texts.status(active, "L"), texts.status(expired, "L"),
        texts.home(active), texts.home(expired), texts.tariffs(), texts.checkout("1 месяц", 199),
        texts.referral("https://t.me/x"), texts.help_text(1), texts.HOW_IT_WORKS,
    ]


def test_every_screen_has_balanced_html_for_telegram():
    from html.parser import HTMLParser

    class Check(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attrs):
            self.stack.append(tag)

        def handle_endtag(self, tag):
            assert self.stack and self.stack.pop() == tag, tag

    allowed = {"b", "i", "code", "blockquote"}
    for text in _rendered_texts():
        checker = Check()
        checker.feed(text)
        assert not checker.stack, text
        import re
        assert set(re.findall(r"</?([a-z]+)", text)) <= allowed, text


def test_user_name_is_escaped_in_the_greeting():
    text = texts.welcome("<Марат & Ко>")
    assert "&lt;Марат &amp; Ко&gt;" in text and "<Марат" not in text


def test_time_left_and_bar():
    now = 1_800_000_000
    assert core.time_left(now + 2 * 86400 + 14 * 3600 + 59, now) == "2 дня 14 ч"
    assert core.time_left(now + 86400, now) == "1 день"
    assert core.time_left(now + 5 * 3600 + 20 * 60, now) == "5 ч 20 мин"
    assert core.time_left(now + 30, now) == "меньше минуты"
    assert core.time_left(now - 5, now) == "0 мин"
    assert core.bar(3, 10) == "▰▰▰▱▱▱▱▱▱▱"
    assert core.bar(50, 10) == "▰" * 10 and core.bar(1, 0) == "▱" * 10
    assert core.per_month(90, 549) == 183


def test_status_card_shows_time_left_and_traffic_bar():
    access = core.Access("corp_mrt_1", "T", int(time.time()) + 2 * 86400 + 3600 * 5 + 30, "active", 3 * 1024**3, 10 * 1024**3)
    text = texts.status(access, "L")
    assert "Осталось: <b>2 дня 5 ч</b>" in text and "▰▰▰▱▱▱▱▱▱▱ 3,0 из 10,0 ГБ" in text


def test_profile_descriptions_fit_telegram_limits():
    assert len(texts.SHORT_DESCRIPTION) <= 120
    assert len(texts.DESCRIPTION) <= 512


def test_help_lists_every_menu_command():
    from marat_bot import app

    for command in app.COMMANDS:
        assert f"/{command['command']} " in texts.COMMANDS_GUIDE, command


def test_commands_answer_without_access(monkeypatch, tmp_path):
    import asyncio
    from marat_bot import app

    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    tg = _FakeTg()

    async def run():
        for command in ("/connect", "/status", "/tariffs", "/help", "/promo", "/support", "/START"):
            await app.on_message(tg, {"text": command, "chat": {"id": 5}, "from": {"id": 5, "first_name": "Ира"}})

    asyncio.run(run())
    replies = [t for _, t, _ in tg.sent]
    assert replies[0] == texts.NEED_ACCESS and replies[1] == texts.NEED_ACCESS
    assert "Тарифы" in replies[2] and "Команды" in replies[3]
    assert "Привет, Ира!" in replies[-1]
    app._store.cache_clear()


def test_trial_sends_a_separate_message_with_confetti(monkeypatch, tmp_path):
    import asyncio
    from marat_bot import app

    access = core.Access("corp_mrt_5", "T", int(time.time()) + 3 * 86400, "active", 0, 10 * 1024**3)

    async def fake_issue(telegram_id):
        return access, True

    monkeypatch.setattr(app, "_issue_trial", fake_issue)
    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    tg = _FakeTg()
    asyncio.run(app.on_callback(tg, _call("trial")))
    app._store.cache_clear()
    assert "доступ активен" in tg.edits[0][2]
    assert "Доступ открыт" in tg.sent[0][1] and tg.effects == [app.EFFECT_PARTY]


# --- 12.10.2026: админка ---

from marat_bot import admin  # noqa: E402


class _NotFound(Exception):
    pass


class _FakePanel:
    def __init__(self, users):
        self.users = users
        self.modified, self.reset = [], []

    async def list_users(self, limit=1000):
        return [
            {"username": u.username, "status": u.status, "expire": u.expire, "used_traffic": u.used_traffic_bytes,
             "data_limit": u.data_limit_bytes, "online_at": u.online_at}
            for u in self.users.values()
        ] + [{"username": "tg_1", "status": "active", "expire": None, "used_traffic": 10**12, "data_limit": 0}]

    async def get_user(self, username):
        if username not in self.users:
            raise _NotFound(username)
        return self.users[username]

    async def modify_user(self, username, **changes):
        self.modified.append((username, changes))
        user = self.users[username]
        if "expire_at" in changes:
            user.expire = changes["expire_at"]
        if "data_limit_bytes" in changes:
            user.data_limit_bytes = changes["data_limit_bytes"]
        return user

    async def reset_user_data_usage(self, username):
        self.reset.append(username)
        return self.users[username]


class _User:
    def __init__(self, username, expire, status="active", used=0, limit=10 * 1024**3, online_at=None):
        self.username, self.expire, self.status = username, expire, status
        self.used_traffic_bytes, self.data_limit_bytes, self.online_at = used, limit, online_at


def test_admins_are_parsed_from_ids_and_nicknames():
    assert admin.parse_admins("@MaratKam1, 740484324; ,x_y") == (frozenset({740484324}), frozenset({"maratkam1", "x_y"}))


def test_nickname_admin_is_bound_to_the_first_telegram_id(monkeypatch, tmp_path):
    monkeypatch.setattr(admin, "ADMIN_IDS", frozenset())
    monkeypatch.setattr(admin, "ADMIN_NAMES", frozenset({"maratkam1"}))
    store = core.Store(str(tmp_path / "u.sqlite3"))
    assert admin.is_admin(store, {"id": 11, "username": "MaratKam1"})
    assert admin.is_admin(store, {"id": 11, "username": "maratkam1"})
    assert not admin.is_admin(store, {"id": 99, "username": "maratkam1"}), "ник ушёл другому — не админ"
    assert not admin.is_admin(store, {"id": 12, "username": "someone"})
    assert not admin.is_admin(store, {"id": 12})


def _admin_env(monkeypatch, tmp_path, users):
    from marat_bot import app

    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    monkeypatch.setattr(admin, "ADMIN_IDS", frozenset({1}))
    monkeypatch.setattr(admin, "ADMIN_NAMES", frozenset())
    panel = _FakePanel(users)
    monkeypatch.setattr(app, "_panel", lambda: (panel, _NotFound))
    return app, panel


def _msg(text, user=1, **sender):
    return {"text": text, "chat": {"id": user}, "from": {"id": user, **sender}}


def test_non_admin_does_not_get_admin_commands(monkeypatch, tmp_path):
    import asyncio

    app, panel = _admin_env(monkeypatch, tmp_path, {})
    tg = _FakeTg()
    asyncio.run(app.on_message(tg, _msg("/admin", user=5)))
    asyncio.run(app.on_message(tg, _msg("/extend 5 365", user=5)))
    assert all("Админка" not in t for _, t, _ in tg.sent) and not panel.modified
    asyncio.run(app.on_callback(tg, _call("adm", user=5)))
    assert not tg.edits
    app._store.cache_clear()


def test_admin_panel_lists_stats_and_only_bot_users(monkeypatch, tmp_path):
    import asyncio

    now = int(time.time())
    users = {"corp_mrt_7": _User("corp_mrt_7", now + 3600, used=2 * 1024**3, online_at="2099-01-01T00:00:00")}
    app, _ = _admin_env(monkeypatch, tmp_path, users)
    app._store().add(7, "corp_mrt_7")
    app._store().touch(7, "ira_k", "<Ира>")
    tg = _FakeTg()
    asyncio.run(app.on_message(tg, _msg("/admin")))
    asyncio.run(app.on_message(tg, _msg("/users")))
    asyncio.run(app.on_message(tg, _msg("/start")))
    panel_text, users_text, home = (t for _, t, _ in tg.sent)
    assert "Пользователей: <b>1</b>" in panel_text and "Трафик всего: 2,0 ГБ" in panel_text, "чужие учётки не считаются"
    assert "<code>7</code> · &lt;Ира&gt; @ira_k" in users_text
    assert any(b.get("callback_data") == "adm" for row in tg.sent[2][2]["inline_keyboard"] for b in row)
    assert any(m == "setMyCommands" and p.get("scope") == {"type": "chat", "chat_id": 1} for m, p in tg.calls)
    app._store.cache_clear()


def test_extend_adds_days_from_the_later_of_now_and_expiry_and_notifies(monkeypatch, tmp_path):
    import asyncio

    now = int(time.time())
    users = {"corp_mrt_7": _User("corp_mrt_7", now + 86400), "corp_mrt_8": _User("corp_mrt_8", now - 86400, status="expired")}
    app, panel = _admin_env(monkeypatch, tmp_path, users)
    tg = _FakeTg()
    asyncio.run(app.on_message(tg, _msg("/extend 7 30")))
    asyncio.run(app.on_message(tg, _msg("/extend 8 2")))
    assert abs(users["corp_mrt_7"].expire - (now + 31 * 86400)) < 5
    assert abs(users["corp_mrt_8"].expire - (now + 2 * 86400)) < 5
    to_user = [(c, t) for c, t, _ in tg.sent if c in (7, 8)]
    assert len(to_user) == 2 and all("Доступ продлён" in t for _, t in to_user)
    assert sum("✅" in t for c, t, _ in tg.sent if c == 1) == 2
    app._store.cache_clear()


def test_extend_and_traffic_reject_bad_input_and_foreign_users(monkeypatch, tmp_path):
    import asyncio

    app, panel = _admin_env(monkeypatch, tmp_path, {})
    tg = _FakeTg()
    for text in ("/extend", "/extend 7", "/extend 7 0", "/extend 7 366", "/extend abc 5", "/traffic 7 -1", "/traffic 7 99999", "/user"):
        asyncio.run(app.on_message(tg, _msg(text)))
    assert all("Формат" in t for _, t, _ in tg.sent)
    asyncio.run(app.on_message(tg, _msg("/extend 740484324 30")))
    assert "нет в боте" in tg.sent[-1][1] and not panel.modified, "трогает только corp_mrt_*"
    app._store.cache_clear()


def test_traffic_sets_limit_and_resets_counter(monkeypatch, tmp_path):
    import asyncio

    users = {"corp_mrt_7": _User("corp_mrt_7", int(time.time()) + 60, status="limited", used=10 * 1024**3)}
    app, panel = _admin_env(monkeypatch, tmp_path, users)
    tg = _FakeTg()
    asyncio.run(app.on_message(tg, _msg("/traffic 7 0")))
    assert panel.modified == [("corp_mrt_7", {"data_limit_bytes": 0})] and panel.reset == ["corp_mrt_7"]
    assert "без лимита" in tg.sent[-1][1]
    asyncio.run(app.on_message(tg, _msg("/user 7")))
    assert "Пользователь" in tg.sent[-1][1]
    app._store.cache_clear()


def test_admin_screens_have_balanced_html(monkeypatch, tmp_path):
    import asyncio
    from html.parser import HTMLParser

    now = int(time.time())
    users = {"corp_mrt_7": _User("corp_mrt_7", now + 3600, online_at="2026-10-12T10:00:00")}
    app, _ = _admin_env(monkeypatch, tmp_path, users)
    app._store().add(7, "corp_mrt_7")
    tg = _FakeTg()
    for text in ("/admin", "/users", "/user 7", "/user 9", "/extend 7 1", "/traffic 7 50"):
        asyncio.run(app.on_message(tg, _msg(text)))

    class Check(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attrs):
            self.stack.append(tag)

        def handle_endtag(self, tag):
            assert self.stack.pop() == tag

    for _, text, _ in tg.sent:
        checker = Check()
        checker.feed(text)
        assert not checker.stack, text
    app._store.cache_clear()
