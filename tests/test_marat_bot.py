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
        return {"message_id": 1000 + len(self.sent)}

    async def copy(self, chat, from_chat, message_id, markup=None, reply_to=None):
        self.copies = [*getattr(self, "copies", []), (chat, from_chat, message_id, markup, reply_to)]
        return 5000 + len(self.copies)

    async def call(self, method, **params):
        self.calls = [*getattr(self, "calls", []), (method, params)]

    async def send_photo(self, chat, path, caption, markup=None, effect=None):
        self.photos = [*getattr(self, "photos", []), (chat, path, caption, markup)]
        self.effects = [*getattr(self, "effects", []), effect]

    async def edit_media(self, chat, msg, path, caption, markup=None):
        if getattr(self, "text_messages", False):
            from marat_bot.tg import TelegramError
            raise TelegramError("editMessageMedia: there is no media in the message to edit")
        self.media_edits = [*getattr(self, "media_edits", []), (chat, msg, path, caption, markup)]

    async def delete(self, chat, msg):
        self.deleted = [*getattr(self, "deleted", []), (chat, msg)]

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


# --- 12.10.2026: темы и второй заказчик («Ярослав VPN») ---

import importlib  # noqa: E402
import inspect  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from marat_bot import themes  # noqa: E402
from marat_bot.themes import classic, orbit  # noqa: E402


def _theme_screens(theme):
    now = int(time.time())
    active = core.Access("corp_yar_1", "T", now + 86400 * 2 + 3600, "active", 2 * 1024**3, 10 * 1024**3)
    limited = core.Access("corp_yar_1", "T", now + 3600, "limited", 10 * 1024**3, 10 * 1024**3)
    return [
        theme.welcome("<b>Яр</b>"), theme.welcome(None), theme.issued("1 января"), theme.ALREADY, theme.PICK_DEVICE,
        theme.steps("Android", "https://x/sub/T"), theme.status(active, "L"), theme.status(limited, "L"),
        theme.home(active), theme.home(limited), theme.tariffs(), theme.checkout("1 месяц", 199),
        theme.referral("https://t.me/x"), theme.help_text(1), theme.HOW_IT_WORKS, theme.NEED_ACCESS, theme.ERROR,
    ]


def test_every_theme_has_the_full_interface():
    for name in themes.THEMES:
        assert themes.load(name)
    try:
        themes.load("nope")
    except SystemExit as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("неизвестная тема должна останавливать службу")


def test_orbit_screens_are_valid_html_and_unbranded():
    import re
    from html.parser import HTMLParser

    for text in _theme_screens(orbit) + [orbit.DESCRIPTION, orbit.SHORT_DESCRIPTION]:
        parser = HTMLParser()
        stack = []
        parser.handle_starttag = lambda tag, attrs: stack.append(tag)
        parser.handle_endtag = lambda tag: stack.pop() == tag or (_ for _ in ()).throw(AssertionError(tag))
        parser.feed(text)
        assert not stack, text
        assert set(re.findall(r"</?([a-z]+)", text)) <= {"b", "i", "code", "blockquote"}, text
        assert "unlock" not in text.lower() and "анлок" not in text.lower(), text
    assert "&lt;b&gt;Яр&lt;/b&gt;" in orbit.welcome("<b>Яр</b>")
    assert len(orbit.SHORT_DESCRIPTION) <= 120 and len(orbit.DESCRIPTION) <= 512


def test_orbit_looks_different_from_classic():
    assert orbit.welcome("Яр") != classic.welcome("Яр")
    from marat_bot.themes.common import DOC_BUTTONS

    # Кнопки документов и поддержки общие намеренно — сравниваем только оформление темы.
    same = {k for k in themes.BUTTON_KEYS if k not in DOC_BUTTONS and orbit.BUTTONS[k] == classic.BUTTONS[k]}
    assert len(same) <= 4, same
    assert "●" in orbit.status(core.Access("corp_yar_1", "T", int(time.time()) + 60, "active", 5 * 1024**3, 10 * 1024**3), "L")


def test_theme_code_never_names_another_customer():
    for module in (orbit, themes.common, sys.modules["marat_bot.keyboards"], admin):
        source = inspect.getsource(module)
        body = source.split('"""', 2)[-1] if source.startswith('"""') else source
        assert "Марат" not in body and "corp_mrt" not in body, module.__name__


def test_orbit_buttons_all_have_handlers(monkeypatch):
    from marat_bot import app, keyboards as kb, texts

    monkeypatch.setattr(texts, "BUTTONS", orbit.BUTTONS)
    for markup in _all_keyboards():
        for data in kb.callbacks(markup):
            assert data in app.HANDLED or data.startswith(app.HANDLED_PREFIXES), data
    assert kb.main(None)["inline_keyboard"][0][0]["text"].startswith("🚀")


def _import_core(env):
    code = "import marat_bot.core as c, marat_bot.texts as t; print(c.NAME, c.panel_username(8569423496), t.THEME)"
    full_env = {**os.environ, "MARAT_DB": "/tmp/unused.sqlite3", **env}
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=full_env,
                          cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_second_bot_is_configured_by_environment():
    ok = _import_core({"MARAT_NAME": "Ярослав VPN", "MARAT_PREFIX": "corp_yar_", "MARAT_THEME": "orbit"})
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.split() == ["Ярослав", "VPN", "corp_yar_8569423496", "orbit"]
    import re
    assert re.fullmatch(r"(corp|exp|ind)_[a-z0-9_]{1,24}", "corp_yar_8569423496")
    for bad in ("tg_", "corp_yaroslavvpn_", "corp_Yar_", "corp_yar"):
        res = _import_core({"MARAT_PREFIX": bad})
        assert res.returncode != 0 and "MARAT_PREFIX" in res.stderr, bad
    assert _import_core({"MARAT_THEME": "neon"}).returncode != 0


# --- 13.10.2026: тема etalon («Etalon VPN») с баннерами ---

from marat_bot.themes import etalon  # noqa: E402


def test_etalon_banners_exist_and_every_caption_fits():
    from marat_bot import app

    for screen, path in etalon.BANNERS.items():
        assert os.path.isfile(path), (screen, path)
    access = core.Access("corp_mrt_1", "T" * 22, int(time.time()) + 86400, "active", 1024**3, 10 * 1024**3)
    long_link = "https://m.212.233.122.241.sslip.io/sub/" + "x" * 60
    screens = {
        "home": etalon.welcome("Константин Константинопольский"), "issued": etalon.issued("31 декабря, 23:59 МСК"),
        "connect": etalon.PICK_DEVICE, "steps": etalon.steps("iPhone / iPad", long_link),
        "status": etalon.status(access, long_link), "tariffs": etalon.tariffs(), "checkout": etalon.checkout("12 месяцев", 1799),
        "help": etalon.help_text(8988612696), "how": etalon.HOW_IT_WORKS, "ref": etalon.referral("https://t.me/x?start=ref1"),
    }
    import html as _html
    import re as _re
    for screen, text in screens.items():
        visible = _html.unescape(_re.sub(r"<[^>]+>", "", text))
        assert len(visible.encode("utf-16-le")) // 2 <= app.CAPTION_LIMIT, (screen, len(visible))


def test_etalon_texts_are_valid_and_unbranded():
    for text in _theme_screens(etalon) + [etalon.DESCRIPTION, etalon.SHORT_DESCRIPTION]:
        assert "unlock" not in text.lower() and "анлок" not in text.lower(), text
    assert len(etalon.SHORT_DESCRIPTION) <= 120 and len(etalon.DESCRIPTION) <= 512
    assert themes.load("etalon").BUTTONS["trial"].startswith("🔑")
    body = inspect.getsource(etalon).split('"""', 2)[-1]
    assert "Марат" not in body, "имя бота — только из MARAT_NAME"


def test_screens_use_banners_and_fall_back_to_new_message(monkeypatch, tmp_path):
    import asyncio
    from marat_bot import app, texts

    monkeypatch.setattr(texts, "BANNERS", etalon.BANNERS)
    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    tg = _FakeTg()
    asyncio.run(app.on_message(tg, {"text": "/start", "chat": {"id": 5}, "from": {"id": 5}}))
    assert tg.photos and tg.photos[0][1].endswith("home.jpg") and not tg.sent
    asyncio.run(app.on_callback(tg, _call("tariffs")))
    assert tg.media_edits[-1][2].endswith("tariffs.jpg")
    tg.text_messages = True
    asyncio.run(app.on_callback(tg, _call("how")))
    assert tg.photos[-1][1].endswith("how.jpg") and tg.deleted == [(5, 7)], "старое сообщение заменено новым"
    long_text = "x" * 2000
    asyncio.run(app.send_screen(tg, 5, "help", long_text))
    assert tg.sent[-1][1] == long_text, "длинная подпись — обычным текстом"
    app._store.cache_clear()


# --- 13.10.2026: тема plata («Plata VPN», бывший «Ярослав VPN») ---

from marat_bot.themes import plata  # noqa: E402


def test_plata_banners_exist_captions_fit_and_texts_are_clean():
    import html as _html
    import re as _re
    from marat_bot import app

    for path in plata.BANNERS.values():
        assert os.path.isfile(path) and "/plata/" in path, path
    access = core.Access("corp_yar_1", "T" * 22, int(time.time()) + 86400, "active", 1024**3, 10 * 1024**3)
    link = "https://y.212.233.122.241.sslip.io/sub/" + "x" * 60
    for text in (plata.welcome("Константин Константинопольский"), plata.steps("iPhone / iPad", link),
                 plata.status(access, link), plata.help_text(8569423496), plata.tariffs(), plata.HOW_IT_WORKS):
        visible = _html.unescape(_re.sub(r"<[^>]+>", "", text))
        assert len(visible.encode("utf-16-le")) // 2 <= app.CAPTION_LIMIT
    for text in _theme_screens(plata) + [plata.DESCRIPTION, plata.SHORT_DESCRIPTION]:
        assert "unlock" not in text.lower() and "эталон" not in text.lower(), text
    body = inspect.getsource(plata).split('"""', 2)[-1]
    assert "Ярослав" not in body and "Марат" not in body
    assert plata.BUTTONS["trial"].startswith("🛡") and len(plata.SHORT_DESCRIPTION) <= 120


# --- 13.10.2026: поддержка в боте и документы (требование платёжного провайдера) ---

from marat_bot import docs, support  # noqa: E402


def _support_env(monkeypatch, tmp_path, admins=frozenset({1})):
    from marat_bot import app

    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    monkeypatch.setattr(admin, "ADMIN_IDS", admins)
    monkeypatch.setattr(admin, "ADMIN_NAMES", frozenset())
    monkeypatch.setattr(support, "_windows", {})
    return app


def _user_msg(text, user=5, message_id=70, **extra):
    return {"message_id": message_id, "text": text, "chat": {"id": user},
            "from": {"id": user, "first_name": "Ира", "username": "ira"}, **extra}


def test_support_message_reaches_admin_and_the_reply_comes_back(monkeypatch, tmp_path):
    import asyncio

    app = _support_env(monkeypatch, tmp_path)
    tg = _FakeTg()

    async def run():
        await app.on_callback(tg, _call("support"))
        await app.on_message(tg, _user_msg("Не подключается на iPhone", message_id=71))
        await app.on_message(tg, {"message_id": 72, "photo": [{"file_id": "x"}], "chat": {"id": 5}, "from": {"id": 5}})
        card_id = next(i for i, (chat, text, _) in enumerate(tg.sent, start=1001) if chat == 1 and "Обращение" in text)
        await app.on_message(tg, {"message_id": 9, "text": "Обновите подписку", "chat": {"id": 1},
                                  "from": {"id": 1}, "reply_to_message": {"message_id": card_id}})
        return card_id

    card_id = asyncio.run(run())
    app._store.cache_clear()
    assert support.PROMPT in [e[2] for e in tg.edits]
    cards = [t for chat, t, _ in tg.sent if chat == 1 and "Обращение" in t]
    assert len(cards) == 1 and "@ira" in cards[0] and "<code>5</code>" in cards[0], "одна карточка на окно"
    to_admin = [c for c in tg.copies if c[0] == 1]
    assert [(c[1], c[2], c[4]) for c in to_admin] == [(5, 71, card_id), (5, 72, card_id)]
    assert [t for chat, t, _ in tg.sent if chat == 5].count(support.SENT) == 2
    answer = [c for c in tg.copies if c[0] == 5]
    assert answer and answer[0][1:3] == (1, 9) and "support" in kb_callbacks(answer[0][3])
    assert (5, support.ANSWER, None) in tg.sent and (1, "✅ Ответ отправлен.", None) in tg.sent


def kb_callbacks(markup):
    from marat_bot import keyboards as kb

    return kb.callbacks(markup)


def test_admin_can_reply_to_the_copied_message_too(monkeypatch, tmp_path):
    import asyncio

    app = _support_env(monkeypatch, tmp_path)
    tg = _FakeTg()

    async def run():
        await app.on_message(tg, _user_msg("/support"))
        await app.on_message(tg, _user_msg("Вопрос по оплате", message_id=80))
        copy_id = 5000 + len(tg.copies)  # id последней копии у админа (см. _FakeTg.copy)
        await app.on_message(tg, {"message_id": 11, "text": "Ок", "chat": {"id": 1}, "from": {"id": 1},
                                  "reply_to_message": {"message_id": copy_id}})

    asyncio.run(run())
    app._store.cache_clear()
    assert any(c[0] == 5 and c[2] == 11 for c in tg.copies)


def test_messages_outside_the_window_are_not_forwarded(monkeypatch, tmp_path):
    import asyncio

    app = _support_env(monkeypatch, tmp_path)
    tg = _FakeTg()

    async def run():
        await app.on_message(tg, _user_msg("привет"))
        await app.on_message(tg, _user_msg("/support"))
        await app.on_message(tg, _user_msg("/start"))
        await app.on_message(tg, _user_msg("ещё привет"))

    asyncio.run(run())
    app._store.cache_clear()
    assert not getattr(tg, "copies", []), "команда закрывает обращение, без окна ничего не уходит"


def test_support_window_expires_and_limits_flood(monkeypatch):
    monkeypatch.setattr(support, "_windows", {})
    support.open_window(5, now=1000)
    assert support.is_open(5, now=1000 + support.WINDOW_SECONDS - 1)
    assert not support.is_open(5, now=1000 + support.WINDOW_SECONDS + 1)

    import asyncio

    class _Store:
        def admin_id(self, name):
            return None

        def get(self, user):
            return None

        def link_support(self, *args):
            pass

    monkeypatch.setattr(admin, "ADMIN_IDS", frozenset({1}))
    monkeypatch.setattr(admin, "ADMIN_NAMES", frozenset())
    support.open_window(5)
    tg = _FakeTg()
    replies = [asyncio.run(support.forward(tg, _Store(), _user_msg("x", message_id=i))) for i in range(12)]
    assert replies[:support.MAX_MESSAGES] == [support.SENT] * support.MAX_MESSAGES
    assert replies[support.MAX_MESSAGES:] == [support.LIMIT] * 2


def test_without_admins_support_stays_a_stub(monkeypatch, tmp_path):
    import asyncio

    app = _support_env(monkeypatch, tmp_path, admins=frozenset())
    tg = _FakeTg()

    async def run():
        await app.on_callback(tg, _call("support"))
        await app.on_message(tg, _user_msg("/support"))

    asyncio.run(run())
    app._store.cache_clear()
    assert (("cb", texts.STUB_SUPPORT, True)) in tg.answers
    assert tg.sent[-1][1] == texts.STUB_SUPPORT and not support._windows


def test_site_link_opens_support(monkeypatch, tmp_path):
    import asyncio

    app = _support_env(monkeypatch, tmp_path)
    tg = _FakeTg()
    asyncio.run(app.on_message(tg, _user_msg("/start support")))
    app._store.cache_clear()
    assert tg.sent[-1][1] == support.PROMPT and support.is_open(5)


def test_docs_buttons_appear_only_with_a_site(monkeypatch):
    from marat_bot import app, keyboards as kb

    monkeypatch.setattr(docs, "SITE_URL", "")
    assert "docs" not in kb.callbacks(kb.main(None)) and docs.checkout_note() == ""

    monkeypatch.setattr(docs, "SITE_URL", "https://etalon.example")
    for markup in (kb.main(None), kb.help_menu()):
        assert "docs" in kb.callbacks(markup)
    urls = [b.get("url") for row in kb.docs_menu()["inline_keyboard"] for b in row]
    assert "https://etalon.example/privacy/" in urls and "https://etalon.example/terms/" in urls
    assert "https://etalon.example/tariffs/" in urls
    assert any(b.get("url") == "https://etalon.example/terms/#refund"
               for row in kb.tariffs()["inline_keyboard"] for b in row)
    assert "пользовательское соглашение" in docs.checkout_note()
    for markup in (kb.docs_menu(), kb.support_prompt(), kb.support_answer(), kb.checkout(), kb.tariffs()):
        for data in kb.callbacks(markup):
            assert data in app.HANDLED or data.startswith(app.HANDLED_PREFIXES), data


def test_docs_screen_is_valid_html(monkeypatch):
    from html.parser import HTMLParser

    monkeypatch.setattr(docs, "SUPPORT_EMAIL", "help@example.com")
    for text in (docs.screen_text(), support.PROMPT, support.ANSWER):
        HTMLParser().feed(text)
        assert text.count("<b>") == text.count("</b>")
    assert "help@example.com" in docs.screen_text()


# --- 13.10.2026: тема avangard («Avangard VPN», бывш. «Avangard GT») ---

from marat_bot.themes import avangard  # noqa: E402


def test_avangard_banners_exist_and_every_caption_fits():
    import html as _html
    import re as _re
    from marat_bot import app

    for screen, path in avangard.BANNERS.items():
        assert os.path.isfile(path), (screen, path)
    access = core.Access("corp_avg_1", "T" * 22, int(time.time()) + 86400, "active", 1024**3, 10 * 1024**3)
    long_link = "https://panel.example.com:8443/sub/" + "x" * 80
    screens = [
        avangard.welcome("Константин Константинопольский"), avangard.issued("31 декабря, 23:59 МСК"),
        avangard.PICK_DEVICE, avangard.steps("iPhone / iPad", long_link), avangard.status(access, long_link),
        avangard.tariffs(), avangard.checkout("12 месяцев", 1799), avangard.help_text(8627023174),
        avangard.HOW_IT_WORKS, avangard.referral("https://t.me/x?start=ref1"),
    ]
    for text in screens:
        visible = _html.unescape(_re.sub(r"<[^>]+>", "", text))
        assert len(visible.encode("utf-16-le")) // 2 <= app.CAPTION_LIMIT, len(visible)


def test_avangard_offers_germany_and_netherlands_in_every_language_and_stays_neutral():
    """14.10.2026: серверы как в тест-ссылке заказчика — 🇩🇪 Германия, 🇳🇱 Нидерланды и авто, без РУ-режима."""
    from marat_bot.themes import avangard_strings as strings

    keys = set(strings.STRINGS["ru"])
    others = ("🇵🇱", "🇫🇮", "🇺🇸", "🇷🇺", "РУ-серв", "ru services", "俄罗斯服务", "سرویس‌های روسی")
    for lang in strings.LANGUAGES:
        t = avangard.localized(lang)
        assert set(strings.STRINGS[lang]) == keys, lang
        assert set(strings.STRINGS[lang]["buttons"]) == set(strings.STRINGS["ru"]["buttons"]), lang
        assert "🇩🇪 🇳🇱" in t.welcome() and "🇩🇪 🇳🇱" in t.tariffs() and "🇩🇪 🇳🇱" in t.help_text(1), lang
        screens = [t.welcome("Ян"), t.issued("1"), t.PICK_DEVICE, t.steps("Android", "L"), t.tariffs(),
                   t.checkout("1", 199), t.referral("L"), t.help_text(1), t.HOW_IT_WORKS, t.DESCRIPTION,
                   t.SHORT_DESCRIPTION]
        for text in screens:
            low = text.lower()
            assert "unlock" not in low and not [w for w in _RISKY if w in low], (lang, text[:60])
            assert not [w for w in others if w.lower() in low], (lang, text[:60])
        assert len(t.SHORT_DESCRIPTION) <= 120 and len(t.DESCRIPTION) <= 512, lang
    body = inspect.getsource(avangard).split('"""', 2)[-1]
    assert "Марат" not in body and "Etalon" not in body


def test_inbounds_and_panel_come_from_the_environment():
    code = (
        "import marat_bot.core as c, marat_bot.app as a; "
        "client, _ = a._panel(); print(c.INBOUNDS['vless']); print(client.base_url, client.username)"
    )
    env = {**os.environ, "MARAT_INBOUNDS": "VLESS DE, VLESS NL ", "MARAT_PANEL_URL": "https://panel.example:8443/",
           "MARAT_PANEL_USERNAME": "avangard", "MARAT_PANEL_PASSWORD": "x", "MARAT_THEME": "avangard",
           "MARAT_PREFIX": "corp_avg_"}
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == ["['VLESS DE', 'VLESS NL']", "https://panel.example:8443 avangard"]


# --- 13.10.2026: формулировки для платёжных провайдеров (Platega, ЮKassa) ---

from marat_bot.themes import plata  # noqa: E402

_RISKY = ("заблокир", "блокиров", "youtube", "instagram", "chatgpt", "без границ", "свободного интернета",
          "не открывается", "без ограничений")


def test_branded_bots_never_advertise_bypassing_blocks():
    for theme in (etalon, plata, avangard):
        for text in _theme_screens(theme) + [theme.DESCRIPTION, theme.SHORT_DESCRIPTION, theme.HOW_IT_WORKS]:
            low = text.lower()
            assert not [w for w in _RISKY if w in low], (theme.__name__, text[:80])


def test_price_per_month_rounds_half_up_like_the_sites():
    assert core.per_month(180, 999) == 167 and core.per_month(90, 549) == 183 and core.per_month(365, 1799) == 148



# --- 14.10.2026: языки интерфейса (Avangard VPN) ---

from marat_bot import i18n  # noqa: E402


def test_language_helpers_speak_every_language():
    assert i18n.days(3, "ru") == "3 дня" and i18n.days(3, "uk") == "3 дні" and i18n.days(1, "en") == "1 day"
    assert i18n.days(5, "uk") == "5 днів" and i18n.days(3, "zh") == "3 天" and i18n.days(3, "fa") == "3 روز"
    now = 1_800_000_000
    assert i18n.left(now + 2 * 86400 + 3600, "en", now=now) == "2 days 1 h"
    assert i18n.left(now + 300, "zh", now=now) == "5 分钟"
    assert "Moscow" in i18n.date_text(now, "en") and "月" in i18n.date_text(now, "zh") and "مسکو" in i18n.date_text(now, "fa")
    assert i18n.guess("ru") == "ru" and i18n.guess("uk") == "uk" and i18n.guess("zh-hans") == "zh"
    assert i18n.guess("fa") == "fa" and i18n.guess("de") == "en" and i18n.guess(None) == "en" and i18n.guess("kk") == "ru"


def test_every_language_screen_fits_a_caption():
    import html as _html
    import re as _re
    from marat_bot import app
    from marat_bot.themes import avangard_strings as strings

    access = core.Access("corp_avg_1", "T" * 22, int(time.time()) + 86400, "active", 1024**3, 10 * 1024**3)
    link = "https://a.212.233.122.241.sslip.io/sub/" + "x" * 60
    for lang in strings.LANGUAGES:
        t = avangard.localized(lang)
        for text in (t.welcome("Константин Константинопольский"), t.issued(t.date_text(int(time.time()))),
                     t.steps("iPhone / iPad", link), t.status(access, link), t.home(access), t.tariffs(),
                     t.help_text(8627023174), t.HOW_IT_WORKS, t.referral(link)):
            visible = _html.unescape(_re.sub(r"<[^>]+>", "", text))
            assert len(visible.encode("utf-16-le")) // 2 <= app.CAPTION_LIMIT, (lang, len(visible))


def _lang_bot(monkeypatch, tmp_path):
    from marat_bot import app, texts

    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    monkeypatch.setattr(texts, "_theme", avangard)
    monkeypatch.setattr(texts, "LANGUAGES", avangard.LANGUAGES)
    monkeypatch.setattr(texts, "BANNERS", {})
    for lang in avangard.LANGUAGES:
        monkeypatch.setattr(avangard.localized(lang), "BANNERS", {})
    return app


def test_first_start_asks_for_the_language_then_speaks_it(monkeypatch, tmp_path):
    import asyncio

    app = _lang_bot(monkeypatch, tmp_path)
    tg = _FakeTg()

    async def run():
        await app.on_message(tg, {"text": "/start", "chat": {"id": 5}, "from": {"id": 5, "language_code": "en"}})
        await app.on_callback(tg, _call("lang:zh"))
        await app.on_message(tg, {"text": "/start", "chat": {"id": 5}, "from": {"id": 5, "language_code": "en"}})

    asyncio.run(run())
    app._store.cache_clear()
    prompt, picker = tg.sent[0][1], tg.sent[0][2]
    assert prompt == avangard.localized("en").LANG_PROMPT, "первый /start — выбор языка, на языке Telegram"
    labels = [b["text"] for row in picker["inline_keyboard"] for b in row]
    assert labels == ["🇷🇺 Русский", "✅ 🇬🇧 English", "🇺🇦 Українська", "🇨🇳 中文", "🇮🇷 فارسی"], "без «Назад» при первом входе"
    assert "中文" in tg.edits[0][2], "сообщение с выбором стало «язык установлен»"
    assert tg.edits[0][3] == {"inline_keyboard": [[{"text": "🌐 更改语言", "callback_data": "lang"}]]}, \
        "нажал не тот язык — под подтверждением кнопка сменить"
    assert "你好" in tg.sent[1][1] and "你好" in tg.sent[2][1], "дальше — на выбранном языке, повторно не спрашиваем"


def test_language_can_be_changed_from_the_menu_with_a_back_button(monkeypatch, tmp_path):
    import asyncio

    app = _lang_bot(monkeypatch, tmp_path)
    app._store().set_lang(5, "uk")
    tg = _FakeTg()

    async def run():
        await app.on_message(tg, {"text": "/language", "chat": {"id": 5}, "from": {"id": 5}})
        await app.on_callback(tg, _call("lang"))

    asyncio.run(run())
    app._store.cache_clear()
    for markup in (tg.sent[0][2], tg.edits[0][3]):
        rows = markup["inline_keyboard"]
        assert rows[-1][0]["text"] == "⬅️ Назад" and rows[-1][0]["callback_data"] == "menu"
        assert any(b["text"].startswith("✅ 🇺🇦") for row in rows for b in row)


def test_main_menu_offers_the_language_only_in_multilingual_bots(monkeypatch, tmp_path):
    """14.10.2026: «если перепутал и не туда нажал» — язык меняется прямо из главного меню."""
    from marat_bot import keyboards, texts

    app = _lang_bot(monkeypatch, tmp_path)
    access = core.Access("corp_avg_1", "T" * 22, int(time.time()) + 86400, "active", 0, 10 * 1024**3)
    for lang, label in (("ru", "🌐 Язык"), ("fa", "🌐 زبان")):
        texts.use(lang)
        for state in (None, access):
            rows = keyboards.main(state)["inline_keyboard"]
            assert {"text": label, "callback_data": "lang"} in [b for row in rows for b in row], (lang, state)
    assert "lang" in app.HANDLED
    monkeypatch.setattr(texts, "LANGUAGES", {})
    texts.use("ru")
    assert "lang" not in keyboards.callbacks(keyboards.main(None)), "у одноязычных Etalon и Plata кнопки нет"


def test_single_language_bots_never_ask(monkeypatch, tmp_path):
    import asyncio
    from marat_bot import app, texts

    monkeypatch.setenv("MARAT_DB", str(tmp_path / "u.sqlite3"))
    app._store.cache_clear()
    assert texts.LANGUAGES == {}
    tg = _FakeTg()
    asyncio.run(app.on_message(tg, {"text": "/start", "chat": {"id": 5}, "from": {"id": 5, "language_code": "en"}}))
    app._store.cache_clear()
    assert "Привет" in tg.sent[0][1], "Etalon и Plata — как раньше, без выбора языка"



def test_every_language_has_its_own_banners():
    for lang in avangard.LANGUAGES:
        banners = avangard.localized(lang).BANNERS
        assert set(banners) == set(avangard.BANNERS), lang
        for screen, path in banners.items():
            assert os.path.isfile(path), (lang, screen, path)
            assert (f"/{lang}/" in path) == (lang != "ru"), (lang, path)


def test_etalon_says_auto_choice_not_bypass():
    """14.10.2026: Platega попросила «Авто-выбор» вместо «Авто-обход» у Etalon."""
    texts_ = _theme_screens(etalon) + [etalon.DESCRIPTION, etalon.SHORT_DESCRIPTION, etalon.HOW_IT_WORKS]
    assert not [t for t in texts_ if "обход" in t.lower()]
    assert any("Авто-выбор" in t for t in texts_)


def test_avangard_speaks_the_castle_brand_not_racing():
    """14.10.2026: фирменный лист «Замок» — никаких «тест-драйвов», гаражей и баков; авто-режим назван как на баннерах."""
    from marat_bot.themes import avangard_strings as strings

    racing = ("тест-драйв", "гараж", "трас", "бак ", "заезд", "заїзд", "test drive", "garage", "on track", "tank",
              "race", "试驾", "车库", "油箱", "比赛", "行驶", "تست‌درایو", "گاراژ", "مسابقه", "باک", "🏁", "⛽", "обход")
    auto = {"ru": "Авто-выбор", "en": "Auto mode", "uk": "Авто-вибір", "zh": "自动选择", "fa": "انتخاب خودکار"}
    for lang in strings.LANGUAGES:
        t = avangard.localized(lang)
        access = core.Access("corp_avg_1", "T" * 22, int(time.time()) + 86400, "active", 1024**3, 10 * 1024**3)
        screens = [t.welcome("Ян"), t.issued("1"), t.steps("Android", "L"), t.status(access, "L"), t.home(access),
                   t.tariffs(), t.checkout("1", 199), t.referral("L"), t.help_text(1), t.HOW_IT_WORKS, t.DESCRIPTION,
                   t.SHORT_DESCRIPTION, t.NEED_ACCESS, t.ALREADY, *t.BUTTONS.values()]
        found = [(word, text[:50]) for text in screens for word in racing if word in text.lower()]
        assert not found, (lang, found)
        assert auto[lang] in t.steps("Android", "L") and auto[lang] in t.tariffs(), lang
    assert avangard.LOOK.full == "▰" and avangard.LOOK.empty == "▱"
