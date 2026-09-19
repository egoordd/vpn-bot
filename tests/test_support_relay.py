"""Поддержка: обращения видят все сотрудники, ответить может любой из них.

19.09.2026 владелец добавил второго сотрудника (@edismee). Раньше обращение
уходило в один чат, и ответ принимался только оттуда. Теперь копия уходит
каждому сотруднику, ответ из любого чата доставляется клиенту, а остальным
приходит пометка, кто и что ответил — чтобы клиенту не ответили дважды.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services import support_relay

OWNER = 740484324
AGENT = 8563480666
STRANGER = 5555
CLIENT = 1144752539


class FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value if isinstance(value, str) else str(value)

    async def get(self, key):
        value = self.data.get(key)
        return value.encode() if value is not None else None


def _reports_bot():
    counter = iter(range(100, 1000))
    bot = SimpleNamespace()
    bot.send_message = AsyncMock(side_effect=lambda chat, text, **kw: SimpleNamespace(message_id=next(counter)))
    return bot


def _client_message(text="Не работает VPN"):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=CLIENT, username="client", full_name="Клиент"),
        answer=AsyncMock(),
    )


def _reply(chat_id: int, to_message_id: int, text: str, username: str = "edismee"):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=chat_id, username=username, full_name="Сотрудник"),
        reply_to_message=SimpleNamespace(message_id=to_message_id),
        text=text,
        caption=None,
        reply=AsyncMock(),
    )


def test_support_chats_put_the_owner_first_and_drop_duplicates():
    assert support_relay.support_chats("740484324", [AGENT, OWNER, AGENT]) == [OWNER, AGENT]
    assert support_relay.support_chats("740484324", []) == [OWNER]


@pytest.mark.asyncio
async def test_every_agent_gets_the_ticket():
    book = support_relay.TicketBook(FakeRedis())
    reports = _reports_bot()

    await support_relay.forward_ticket(_client_message(), reports_bot=reports, book=book, chats=[OWNER, AGENT])

    assert [call.args[0] for call in reports.send_message.await_args_list] == [OWNER, AGENT]
    assert "Не работает VPN" in reports.send_message.await_args_list[1].args[1]


@pytest.mark.asyncio
async def test_an_agent_who_never_opened_the_bot_does_not_lose_the_ticket_for_others():
    book = support_relay.TicketBook(FakeRedis())
    reports = _reports_bot()
    good = reports.send_message.side_effect

    async def send(chat, text, **kw):
        if chat == AGENT:
            raise RuntimeError("Forbidden: bot can't initiate conversation with a user")
        return good(chat, text, **kw)

    reports.send_message = AsyncMock(side_effect=send)
    message = _client_message()

    await support_relay.forward_ticket(message, reports_bot=reports, book=book, chats=[OWNER, AGENT])

    message.answer.assert_awaited_once()
    assert "отправлено" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_agent_reply_reaches_the_client_and_the_owner_sees_who_answered():
    book = support_relay.TicketBook(FakeRedis())
    reports = _reports_bot()
    await support_relay.forward_ticket(_client_message(), reports_bot=reports, book=book, chats=[OWNER, AGENT])
    owner_copy, agent_copy = 100, 101
    support = SimpleNamespace(send_message=AsyncMock())

    reply = _reply(AGENT, agent_copy, "Здравствуйте! Обновите подписку.")
    await support_relay.relay_reply(reply, support_bot=support, reports_bot=reports, book=book, chats=[OWNER, AGENT])

    support.send_message.assert_awaited_once()
    assert support.send_message.await_args.args[0] == CLIENT
    assert "Обновите подписку" in support.send_message.await_args.args[1]
    reply.reply.assert_awaited_once()
    note = reports.send_message.await_args_list[-1]
    assert note.args[0] == OWNER and note.kwargs["reply_to_message_id"] == owner_copy
    assert "@edismee" in note.args[1] and "Обновите подписку" in note.args[1]


@pytest.mark.asyncio
async def test_a_reply_from_anyone_else_is_ignored():
    book = support_relay.TicketBook(FakeRedis())
    reports = _reports_bot()
    await support_relay.forward_ticket(_client_message(), reports_bot=reports, book=book, chats=[OWNER, AGENT])
    support = SimpleNamespace(send_message=AsyncMock())

    await support_relay.relay_reply(
        _reply(STRANGER, 100, "чужой ответ"), support_bot=support, reports_bot=reports, book=book, chats=[OWNER, AGENT]
    )

    support.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_tickets_from_before_the_change_can_still_be_answered_by_the_owner():
    redis = FakeRedis()
    await redis.set("support:ticket:77", CLIENT)
    book = support_relay.TicketBook(redis)
    support = SimpleNamespace(send_message=AsyncMock())

    await support_relay.relay_reply(
        _reply(OWNER, 77, "Ответ на старое обращение", username="owner"),
        support_bot=support, reports_bot=_reports_bot(), book=book, chats=[OWNER, AGENT],
    )

    assert support.send_message.await_args.args[0] == CLIENT


def test_settings_read_the_agent_list(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "SUPPORT_AGENT_IDS", "8563480666, 12")
    assert settings.support_agent_ids == [8563480666, 12]
    monkeypatch.setattr(settings, "SUPPORT_AGENT_IDS", "")
    assert settings.support_agent_ids == []


def test_ticket_record_is_json():
    assert json.loads(support_relay._record(CLIENT, "t1")) == {"user": CLIENT, "ticket": "t1"}
