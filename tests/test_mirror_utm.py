"""/utm в зеркале: свои рекламные ссылки, свой учёт, только аккаунты зеркала.

Основной бот и зеркало пишут в одну базу, но рекламу закупают порознь: ссылка
зеркала должна вести в зеркало и считать только людей зеркала, иначе по ней не
понять, окупилась ли закупка.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from database.repository import Repository
from services import mirror_bot, mirror_utm
from tests.test_mirror_bot import RESTRICTED_VOCABULARY
from tests.test_mirror_platega import FakeTelegram

ADMIN = 740484324
STRANGER = 5555
MIRROR = "UnLockFreedom_bot"


def _message(telegram_id: int, text: str) -> dict:
    return {"from": {"id": telegram_id, "username": f"u{telegram_id}"}, "chat": {"id": telegram_id}, "text": text}


def _texts(telegram: FakeTelegram) -> list[str]:
    return [p.get("text", "") for m, p in telegram.calls if m in {"sendMessage", "editMessageText"}]


def _bot(session_pool) -> tuple[mirror_bot.MirrorBot, FakeTelegram]:
    telegram = FakeTelegram()
    bot = mirror_bot.MirrorBot(telegram, session_pool)
    bot.username = MIRROR
    return bot, telegram


@pytest.mark.asyncio
async def test_admin_issues_a_link_into_the_mirror(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_bot.settings, "ADMIN_IDS", str(ADMIN))
    bot, telegram = _bot(session_pool)

    await bot.handle_message(_message(ADMIN, "/utm Канал <Анна>"))

    reply = _texts(telegram)[-1]
    code = re.search(rf"t\.me/{MIRROR}\?start=utm_([a-z0-9]{{8}})", reply).group(1)
    assert "Канал &lt;Анна&gt;" in reply
    async with session_pool() as session:
        link = await mirror_utm.get(session, code)
    assert link is not None and link.created_by == ADMIN


@pytest.mark.asyncio
async def test_any_user_issues_links_and_sees_only_their_own(session_pool, monkeypatch):
    """18.09.2026: владелец открыл /utm всем пользователям зеркала. Каждый видит
    только свои ссылки — чужие названия и оплаты ему знать незачем."""
    monkeypatch.setattr(mirror_bot.settings, "ADMIN_IDS", str(ADMIN))
    bot, telegram = _bot(session_pool)

    await bot.handle_message(_message(ADMIN, "/utm Ссылка админа"))
    await bot.handle_message(_message(STRANGER, "/utm Моя ссылка"))
    assert re.search(rf"t\.me/{MIRROR}\?start=utm_[a-z0-9]{{8}}", _texts(telegram)[-1])

    await bot.handle_message(_message(STRANGER, "/utm"))
    mine = _texts(telegram)[-1]
    assert "Моя ссылка" in mine and "Ссылка админа" not in mine

    await bot.handle_message(_message(ADMIN, "/utm"))
    admins_own = _texts(telegram)[-1]
    assert "Ссылка админа" in admins_own and "Моя ссылка" not in admins_own, "у админа /utm — тоже только свои"


@pytest.mark.asyncio
async def test_utm_all_shows_everyone_to_admins_only(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_bot.settings, "ADMIN_IDS", str(ADMIN))
    bot, telegram = _bot(session_pool)
    await bot.handle_message(_message(ADMIN, "/utm Ссылка админа"))
    await bot.handle_message(_message(STRANGER, "/utm Моя ссылка"))

    await bot.handle_message(_message(ADMIN, "/utm_all"))
    everything = _texts(telegram)[-1]
    assert "Моя ссылка" in everything and "Ссылка админа" in everything
    assert f"<code>{STRANGER}</code>" in everything, "админу видно, чья ссылка"

    await bot.handle_message(_message(STRANGER, "/utm_all"))
    assert "Ссылка админа" not in _texts(telegram)[-1], "остальным — меню, без намёка на команду"


@pytest.mark.asyncio
async def test_a_user_cannot_flood_the_table(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_bot.settings, "ADMIN_IDS", str(ADMIN))
    monkeypatch.setattr(mirror_utm, "MAX_LINKS_PER_USER", 2)
    bot, telegram = _bot(session_pool)

    for n in range(3):
        await bot.handle_message(_message(STRANGER, f"/utm Ссылка {n}"))

    assert "не больше 2" in _texts(telegram)[-1]
    async with session_pool() as session:
        _, total = await mirror_utm.collect(session, created_by=STRANGER)
    assert total == 2


@pytest.mark.asyncio
async def test_start_by_link_counts_visits_and_tags_only_newcomers(session_pool):
    bot, _ = _bot(session_pool)
    async with session_pool() as session:
        link = await mirror_utm.create(session, title="Реклама", created_by=ADMIN)
        old = await Repository(session).get_or_create_user(mirror_bot.mirror_account_id(8300), "old")
        old_id = old.id

    await bot.record_start({"id": 8301, "username": "new"}, f"utm_{link.code}")
    await bot.record_start({"id": 8301, "username": "new"}, f"utm_{link.code}")
    await bot.record_start({"id": 8300, "username": "old"}, f"utm_{link.code}")
    await bot.record_start({"id": 8302, "username": "x"}, "utm_zzzzzzzz")

    async with session_pool() as session:
        repo = Repository(session)
        newcomer = await repo.get_user_by_telegram_id(mirror_bot.mirror_account_id(8301))
        assert newcomer.source == f"utm_{link.code}"
        assert (await repo.get_user(old_id)).source is None
        assert (await repo.get_user_by_telegram_id(mirror_bot.mirror_account_id(8302))).source is None
        visits = (await session.execute(
            select(mirror_utm.MirrorUtmVisit).order_by(mirror_utm.MirrorUtmVisit.id)
        )).scalars().all()
        assert [(v.user_id, v.is_new_user) for v in visits] == [
            (newcomer.id, True), (newcomer.id, False), (old_id, False),
        ]


@pytest.mark.asyncio
async def test_list_counts_only_what_the_mirror_link_brought(session_pool, monkeypatch):
    monkeypatch.setattr(mirror_bot.settings, "ADMIN_IDS", str(ADMIN))
    bot, telegram = _bot(session_pool)
    async with session_pool() as session:
        link = await mirror_utm.create(session, title="Реклама", created_by=ADMIN)
    for telegram_id in (8401, 8402):
        await bot.record_start({"id": telegram_id, "username": "u"}, f"utm_{link.code}")

    async with session_pool() as session:
        repo = Repository(session)
        now = datetime.now(timezone.utc)
        buyer = await repo.get_user_by_telegram_id(mirror_bot.mirror_account_id(8401))
        await repo.record_funnel_event(buyer.id, "trial")
        await repo.create_payment(user_id=buyer.id, amount=39900, currency="RUB", status="completed")
        await repo.create_subscription(
            user_id=buyer.id, plan="standard_3m", started_at=now, expires_at=now + timedelta(days=90)
        )
        # Аккаунт основного бота с тем же источником — не зеркало, не считается.
        stranger = await repo.create_user(telegram_id=8403)
        await repo.set_user_source_if_unset(stranger.id, f"utm_{link.code}")
        await repo.create_payment(user_id=stranger.id, amount=119900, currency="RUB", status="completed")
        stats, total = await mirror_utm.collect(session)

    assert total == 1
    assert stats[0] == mirror_utm.LinkStats(
        link=stats[0].link, visits=2, new_users=2, trials=1, paid_users=1, revenue_rub=399
    )

    await bot.handle_message(_message(ADMIN, "/utm"))
    text = _texts(telegram)[-1]
    assert f"t.me/{MIRROR}?start=utm_{link.code}" in text
    assert "Оплатили: 1 на 399 ₽" in text


def test_admin_texts_keep_to_the_mirror_vocabulary():
    link = mirror_utm.MirrorUtmLink(code="t5um7wng", title="Канал", created_by=ADMIN)
    texts = [
        mirror_utm.render_created(link, MIRROR),
        mirror_utm.render_list([mirror_utm.LinkStats(link=link)], 1, MIRROR),
        mirror_utm.render_list([], 0, MIRROR),
        mirror_utm.render_too_many(),
        mirror_utm.render_list([mirror_utm.LinkStats(link=link)], 1, MIRROR, everyone=True),
    ]
    offenders = {word for text in texts for word in RESTRICTED_VOCABULARY if word in text.lower()}
    assert not offenders
