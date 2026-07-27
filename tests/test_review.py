from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import review as review_handler
from database.repository import Repository


@pytest.mark.integration
async def test_create_review_persists(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=5001, username="rev")
        r = await repo.create_review(user_id=user.id, rating=5, text="отличный сервис")
        assert r.id is not None and r.rating == 5
        assert await repo.count_reviews() == 1


@pytest.mark.integration
async def test_review_text_saves_and_alerts_owner(session_pool, monkeypatch):
    async with session_pool() as session:
        await Repository(session).create_user(telegram_id=5002, username="john")

    alert = AsyncMock(return_value=True)
    monkeypatch.setattr(review_handler, "send_alert", alert)

    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"rating": 5}),
        clear=AsyncMock(),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=5002, username="john", full_name="John"),
        text="Пользуюсь месяц, всё стабильно, спасибо за каскад — работает даже когда всё остальное лежит! " * 2,
        answer=AsyncMock(),
    )

    await review_handler.review_text(message, state, session_pool)

    # persisted
    async with session_pool() as session:
        assert await Repository(session).count_reviews() == 1
    # owner notified with identity, and long review flagged as detailed/rewardable
    alert.assert_awaited_once()
    sent = alert.await_args.args[0]
    assert "5002" in sent and "@john" not in sent or "john" in sent
    assert "наградить" in sent  # detailed
    message.answer.assert_awaited()


@pytest.mark.integration
async def test_review_text_short_not_flagged(session_pool, monkeypatch):
    async with session_pool() as session:
        await Repository(session).create_user(telegram_id=5003, username="ann")
    monkeypatch.setattr(review_handler, "send_alert", AsyncMock(return_value=True))
    state = SimpleNamespace(get_data=AsyncMock(return_value={"rating": 4}), clear=AsyncMock())
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=5003, username="ann", full_name="Ann"),
        text="норм",
        answer=AsyncMock(),
    )
    await review_handler.review_text(message, state, session_pool)
    sent = review_handler.send_alert.await_args.args[0]
    assert "наградить" not in sent  # short review, not flagged


def test_rating_keyboard_has_five_stars():
    kb = review_handler._rating_keyboard()
    datas = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
    assert [f"review_rate:{n}" for n in (1, 2, 3, 4, 5)] == [d for d in datas if d.startswith("review_rate:")]
