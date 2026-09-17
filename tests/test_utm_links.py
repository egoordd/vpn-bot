"""Рекламные ссылки /utm: бот выпускает `?start=utm_<код>`, помнит их и считает.

Под каждую закупку рекламы нужна своя ссылка, и придумывать ей имя руками
(`src_ИМЯ`) неудобно: имена повторяются, а по ссылке без записи в базе нельзя
понять, выпускали ли её вообще. Ссылка из /utm живёт в базе, и всё, что сделал
пришедший по ней новый человек, засчитывается ей.
"""

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from bot.handlers import start
from database.models import UtmVisit
from database.repository import Repository
from services import utm_links

BOT = "unlkvpn_bot"


def _start(telegram_id: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text, from_user=SimpleNamespace(id=telegram_id, username=f"u{telegram_id}", full_name="U")
    )


def test_codes_look_like_the_competitors_and_do_not_repeat():
    codes = {utm_links.new_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(re.fullmatch(r"[a-z0-9]{8}", code) for code in codes)
    assert utm_links.start_link(BOT, "t5um7wng") == "https://t.me/unlkvpn_bot?start=utm_t5um7wng"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("utm_t5um7wng", "t5um7wng"),
        (" utm_t5um7wng ", "t5um7wng"),
        ("utm_T5UM7WNG", None),
        ("utm_short", None),
        ("utm_t5um7wng1", None),
        ("src_t5um7wng", None),
        (None, None),
    ],
)
def test_parse_start_payload(payload, code):
    assert utm_links.parse_start_payload(payload) == code


@pytest.mark.integration
async def test_create_stores_link_with_title_and_author(db_session):
    link = await utm_links.create(db_session, title="  Блогер <Иван>  ", created_by=777)

    stored = await utm_links.get(db_session, link.code)
    assert stored is not None
    assert stored.title == "Блогер <Иван>"
    assert stored.created_by == 777
    with pytest.raises(ValueError):
        await utm_links.create(db_session, title="   ", created_by=777)


@pytest.mark.integration
async def test_start_by_link_counts_visit_and_tags_only_new_people(session_pool):
    async with session_pool() as session:
        link = await utm_links.create(session, title="Канал", created_by=777)
        old = await Repository(session).create_user(telegram_id=8100, username="old")
        old_id = old.id

    await start._record_start_event(session_pool, _start(8101, f"/start utm_{link.code}"))
    await start._record_start_event(session_pool, _start(8101, f"/start utm_{link.code}"))
    await start._record_start_event(session_pool, _start(8100, f"/start utm_{link.code}"))
    await start._record_start_event(session_pool, _start(8102, "/start utm_zzzzzzzz"))

    async with session_pool() as session:
        repo = Repository(session)
        newcomer = await repo.get_user_by_telegram_id(8101)
        assert newcomer.source == f"utm_{link.code}"
        assert (await repo.get_user(old_id)).source is None, "старый клиент рекламе не засчитывается"
        assert (await repo.get_user_by_telegram_id(8102)).source is None
        visits = (await session.execute(select(UtmVisit).order_by(UtmVisit.id))).scalars().all()
        assert [(v.user_id, v.is_new_user) for v in visits] == [
            (newcomer.id, True),
            (newcomer.id, False),
            (old_id, False),
        ]


@pytest.mark.integration
async def test_collect_counts_what_each_link_brought(session_pool):
    async with session_pool() as session:
        ads = await utm_links.create(session, title="Реклама", created_by=777)
        quiet = await utm_links.create(session, title="Тишина", created_by=777)

    for telegram_id in (8201, 8202, 8203):
        await start._record_start_event(session_pool, _start(telegram_id, f"/start utm_{ads.code}"))
    await start._record_start_event(session_pool, _start(8201, f"/start utm_{ads.code}"))

    async with session_pool() as session:
        repo = Repository(session)
        now = datetime.now(timezone.utc)
        trial_user = await repo.get_user_by_telegram_id(8202)
        buyer = await repo.get_user_by_telegram_id(8203)
        await repo.record_funnel_event(trial_user.id, "trial")
        await repo.record_funnel_event(buyer.id, "trial")
        await repo.create_payment(user_id=buyer.id, amount=39900, currency="RUB", status="completed")
        await repo.create_payment(user_id=buyer.id, amount=14900, currency="RUB", status="completed")
        await repo.create_payment(user_id=trial_user.id, amount=14900, currency="RUB", status="pending")
        await repo.create_subscription(
            user_id=buyer.id, plan="standard_3m", started_at=now, expires_at=now + timedelta(days=90)
        )

        stats, total = await utm_links.collect(session)

    assert total == 2
    by_code = {item.link.code: item for item in stats}
    assert by_code[ads.code] == utm_links.LinkStats(
        link=by_code[ads.code].link, visits=4, new_users=3, trials=2, paid_users=1, revenue_rub=548
    )
    assert by_code[quiet.code].visits == 0 and by_code[quiet.code].paid_users == 0
    assert [item.link.code for item in stats] == [quiet.code, ads.code], "свежие ссылки сверху"


@pytest.mark.integration
async def test_utm_command_creates_link_and_lists_stats(session_pool, monkeypatch):
    from bot.handlers import admin

    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "777")
    bot = SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(username=BOT)))

    def message(user_id: int, text: str) -> SimpleNamespace:
        return SimpleNamespace(
            text=text, bot=bot, from_user=SimpleNamespace(id=user_id, username="adm"), answer=AsyncMock()
        )

    empty = message(777, "/utm")
    await admin.utm_handler(empty, session_pool)
    assert "/utm &lt;название&gt;" in empty.answer.await_args.args[0]

    created = message(777, "/utm Блогер <Иван>")
    await admin.utm_handler(created, session_pool)
    reply = created.answer.await_args.args[0]
    code = re.search(r"start=utm_([a-z0-9]{8})", reply).group(1)
    assert "Блогер &lt;Иван&gt;" in reply
    assert f"<code>https://t.me/{BOT}?start=utm_{code}</code>" in reply

    listing = message(777, "/utm")
    await admin.utm_handler(listing, session_pool)
    text = listing.answer.await_args.args[0]
    assert "Блогер &lt;Иван&gt;" in text
    assert f"utm_{code}" in text
    assert "Переходов: 0" in text

    stranger = message(5555, "/utm Чужая")
    await admin.utm_handler(stranger, session_pool)
    async with session_pool() as session:
        _, total = await utm_links.collect(session)
    assert total == 1
