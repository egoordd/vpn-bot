"""Handing the subscription link over by mail.

A customer in Russia cannot open Telegram without a working tunnel, so the
screen that hands out the link is unreachable exactly when it is needed —
«чтобы подключить впн надо включить другой», as one of them put it. Mail leaves
the link somewhere that survives losing the tunnel.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import connect_device
from database.repository import Repository


class _State:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.cleared = False

    async def get_data(self):
        return self.data

    async def update_data(self, **kw):
        self.data.update(kw)

    async def set_state(self, *_):
        pass

    async def clear(self):
        self.cleared = True


def _message(text, telegram_id=900900):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=telegram_id, username="tester"),
        answer=AsyncMock(),
    )


@pytest.mark.integration
async def test_a_typo_is_rejected_without_losing_the_flow(session_pool, monkeypatch):
    """Sending the link to a mistyped address is the one failure the customer
    cannot detect: nothing arrives and nothing says why."""
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(connect_device.mailer, "send_email", send)
    message = _message("не почта")
    state = _State({"sub_id": None})

    await connect_device.connect_email_message_handler(message, state, session_pool)

    send.assert_not_awaited()
    assert not state.cleared, "the customer stays in the flow to correct the address"
    assert "не похоже на email" in message.answer.await_args.args[0].lower()


@pytest.mark.integration
async def test_the_link_is_mailed_and_the_address_remembered(session_pool, monkeypatch):
    async with session_pool() as session:
        user = await Repository(session).create_user(telegram_id=900901)
        await session.commit()
        user_id = user.id

    monkeypatch.setattr(
        connect_device, "_active_subs_with_links",
        AsyncMock(return_value=[(SimpleNamespace(id=7), "https://sub.example/sub/tok")]),
    )
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(connect_device.mailer, "send_email", send)

    message = _message("buyer@mail.ru", telegram_id=900901)
    await connect_device.connect_email_message_handler(message, _State({"sub_id": 7}), session_pool)

    send.assert_awaited_once()
    to, subject, text = send.await_args.args[:3]
    assert to == "buyer@mail.ru"
    assert "https://sub.example/sub/tok" in text
    assert "unlockvpn.site/download" in text, "the mail has to carry the app too"

    async with session_pool() as session:
        saved = await Repository(session).get_user(user_id)
        assert saved.email == "buyer@mail.ru", "the address is kept for later recovery"


@pytest.mark.integration
async def test_a_failed_send_is_not_reported_as_success(session_pool, monkeypatch):
    """The whole point is that this copy is reachable when Telegram is not —
    claiming delivery we did not achieve would strand the customer."""
    monkeypatch.setattr(
        connect_device, "_active_subs_with_links",
        AsyncMock(return_value=[(SimpleNamespace(id=1), "https://sub.example/sub/tok")]),
    )
    monkeypatch.setattr(connect_device.mailer, "send_email", AsyncMock(return_value=False))

    message = _message("buyer@mail.ru", telegram_id=900902)
    await connect_device.connect_email_message_handler(message, _State({"sub_id": 1}), session_pool)

    said = message.answer.await_args.args[0].lower()
    assert "не удалось" in said
    assert "отправили" not in said


@pytest.mark.integration
async def test_no_subscription_means_no_mail(session_pool, monkeypatch):
    monkeypatch.setattr(connect_device, "_active_subs_with_links", AsyncMock(return_value=[]))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(connect_device.mailer, "send_email", send)

    message = _message("buyer@mail.ru", telegram_id=900903)
    await connect_device.connect_email_message_handler(message, _State({"sub_id": None}), session_pool)

    send.assert_not_awaited()
    assert "не нашли активную подписку" in message.answer.await_args.args[0].lower()


@pytest.mark.integration
async def test_mailing_the_link_also_opens_the_site_cabinet(session_pool):
    """The two halves have to meet: the bot saves the address on the Telegram
    account, and registering on the site with that same address claims THAT
    account rather than creating a second one. Otherwise we would be telling a
    customer to go to a cabinet that shows an empty account — which is exactly
    how the last support ticket started."""
    from services import billing_api

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=900904)
        await repo.update_user(user.id, email="vladimir@mail.ru")
        await session.commit()
        telegram_id = user.telegram_id

        claimed = await billing_api.register_web_account(
            session, email="vladimir@mail.ru", password="correct horse battery"
        )
        assert claimed == telegram_id, "the cabinet must land on his real account"

        again = await billing_api.authenticate_web_account(
            session, email="vladimir@mail.ru", password="correct horse battery"
        )
        assert again == telegram_id
