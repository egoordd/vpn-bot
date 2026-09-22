"""Покупка на сайте по почте: аккаунт появляется только после оплаты, и пароли к нему.

19.09.2026 владелец попросил: аккаунт — после оплаты, а не до; пароль либо
временный из письма, либо свой; «Забыли пароль?»; а оплату на почту, где уже
есть аккаунт, не запрещать — она продлевает подписку этого аккаунта.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from database.repository import Repository
from services import web_checkout, web_delivery, web_passwords, webauth
from tests.test_http_api import api_client  # noqa: F401 - fixture

PLAN = "standard_1m"


class _Sub:
    subscription_url = "https://23.95.3.18.sslip.io/sub/new-token"
    expires_at = datetime(2026, 10, 19, tzinfo=timezone.utc)


def _created(payment_id: str):
    return AsyncMock(
        return_value={
            "id": payment_id,
            "status": "pending",
            "confirmation": {"confirmation_url": f"https://yoomoney.ru/pay/{payment_id}"},
        }
    )


async def _checkout(client, monkeypatch, email: str, payment_id: str, **extra):
    from services import http_api as api_mod

    monkeypatch.setattr(api_mod.yookassa, "is_configured", lambda: True)
    create = _created(payment_id)
    monkeypatch.setattr(api_mod.yookassa, "create_payment", create)
    response = await client.post("/web/checkout", json={"plan": PLAN, "email": email, **extra})
    return response, create


async def _pay(client, monkeypatch, payment_id: str):
    """Вебхук ЮKassa об успешной оплате. Возвращает (ответ, письмо, выдача)."""
    from services import http_api as api_mod

    monkeypatch.setattr(
        api_mod.yookassa,
        "get_payment",
        AsyncMock(return_value={"id": payment_id, "status": "succeeded", "amount": {"value": "149.00"}}),
    )
    activate = AsyncMock(return_value=_Sub())
    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", AsyncMock(return_value=True))
    letter = AsyncMock(return_value=True)
    monkeypatch.setattr(api_mod.web_delivery, "send_subscription_letter", letter)
    response = await client.post("/yookassa/webhook", json={"object": {"id": payment_id}})
    return response, letter, activate


async def _order_token(session_pool, payment_id: str) -> str:
    async with session_pool() as session:
        return (await web_checkout.find(session, payment_id)).token


async def _store_subscription(session_pool, email: str) -> None:
    """Выдача в тестах подменена — кладём подписку в базу сами, как её кладёт панель."""
    from database.models import Subscription

    async with session_pool() as session:
        user = await Repository(session).get_user_by_email(email)
        session.add(
            Subscription(
                user_id=user.id, plan=PLAN, tier="standard",
                subscription_url=_Sub.subscription_url, expires_at=_Sub.expires_at,
            )
        )
        await session.commit()


async def _login(client, email: str, password: str) -> int:
    response = await client.post("/web/auth/login", json={"email": email, "password": password})
    return response.status_code


# --- аккаунт после оплаты ----------------------------------------------------


@pytest.mark.asyncio
async def test_payment_creates_the_account_with_a_temporary_password(api_client, session_pool, monkeypatch):  # noqa: F811
    await _checkout(api_client, monkeypatch, "new@mail.ru", "yk-new-1")
    token = await _order_token(session_pool, "yk-new-1")

    response, letter, _ = await _pay(api_client, monkeypatch, "yk-new-1")

    assert response.status_code == 200
    letter.assert_awaited_once()
    assert letter.await_args.args[0] == "new@mail.ru"
    assert letter.await_args.kwargs["login_email"] == "new@mail.ru"
    password = letter.await_args.kwargs["temporary_password"]
    assert len(password) == web_checkout.TEMPORARY_PASSWORD_LENGTH
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.get_user_by_email("new@mail.ru")
        assert user is not None and user.telegram_id < 0
        payment = await repo.get_payment_by_external_id("yk-new-1")
        assert payment.status == "completed" and payment.user_id == user.id
        assert payment.invoice_payload == f"unlock:{user.id}:{PLAN}:{token}"
    assert await _login(api_client, "new@mail.ru", password) == 200


@pytest.mark.asyncio
async def test_the_order_page_shows_the_link_to_the_account_it_created(api_client, session_pool, monkeypatch):  # noqa: F811
    await _checkout(api_client, monkeypatch, "page@mail.ru", "yk-page-1")
    token = await _order_token(session_pool, "yk-page-1")

    pending = await api_client.get(f"/web/order/{token}")
    assert pending.json() == {"status": "pending"}

    await _pay(api_client, monkeypatch, "yk-page-1")
    await _store_subscription(session_pool, "page@mail.ru")
    done = (await api_client.get(f"/web/order/{token}")).json()

    assert done["status"] == "succeeded"
    assert done["subscription"]["subscriptionUrl"].endswith("/sub/new-token")
    assert done["account"] == {"email": "page@mail.ru", "isNew": True, "canSetPassword": True}
    # Страница оплаты хранит номер платежа ЮKassa — по нему тоже находится.
    assert (await api_client.get("/web/order/yk-page-1")).json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_the_buyer_can_set_their_own_password_on_the_order_page_once(api_client, session_pool, monkeypatch):  # noqa: F811
    await _checkout(api_client, monkeypatch, "own@mail.ru", "yk-own-1")
    token = await _order_token(session_pool, "yk-own-1")
    await _pay(api_client, monkeypatch, "yk-own-1")

    weak = await api_client.post(f"/web/order/{token}/password", json={"password": "short"})
    assert weak.status_code == 400
    ok = await api_client.post(f"/web/order/{token}/password", json={"password": "my-own-pass1"})
    assert ok.status_code == 200 and ok.json()["telegramId"] < 0
    assert await _login(api_client, "own@mail.ru", "my-own-pass1") == 200

    # Пароль уже свой: номер заказа больше не даёт его менять.
    again = await api_client.post(f"/web/order/{token}/password", json={"password": "stolen-pass1"})
    assert again.status_code == 409
    assert (await api_client.get(f"/web/order/{token}")).json()["account"]["canSetPassword"] is False


@pytest.mark.asyncio
async def test_the_order_page_password_expires_after_a_day(session_pool, monkeypatch):
    async with session_pool() as session:
        checkout = await web_checkout.start(session, email="late@mail.ru", plan=PLAN, amount_kopecks=14900, source=None)
        await web_checkout.attach_payment(session, checkout, "yk-late-1")
        await web_checkout.fulfill(session, "yk-late-1")
        assert await web_checkout.can_set_password(session, checkout)

        checkout.completed_at = datetime.now(timezone.utc) - web_checkout.SET_PASSWORD_WINDOW - timedelta(minutes=1)
        await session.commit()
        assert not await web_checkout.can_set_password(session, checkout)


@pytest.mark.asyncio
async def test_a_repeated_webhook_delivers_once(api_client, session_pool, monkeypatch):  # noqa: F811
    await _checkout(api_client, monkeypatch, "twice@mail.ru", "yk-twice-1")
    await _pay(api_client, monkeypatch, "yk-twice-1")

    response, letter, activate = await _pay(api_client, monkeypatch, "yk-twice-1")

    assert response.json() == {"ok": True, "already": True}
    activate.assert_not_awaited()
    letter.assert_not_awaited()


# --- почта, на которой уже есть аккаунт ---------------------------------------


@pytest.mark.asyncio
async def test_an_address_with_an_account_asks_first_then_renews_it(api_client, session_pool, monkeypatch):  # noqa: F811
    registered = await api_client.post(
        "/web/auth/register", json={"email": "owner@mail.ru", "password": "owner-pass1"}
    )
    owner_id = registered.json()["telegramId"]

    asked, create = await _checkout(api_client, monkeypatch, "owner@mail.ru", "yk-own-2")
    assert asked.status_code == 409 and asked.json()["detail"] == "account_exists"
    create.assert_not_awaited()

    confirmed, _ = await _checkout(api_client, monkeypatch, "owner@mail.ru", "yk-own-2", confirmExisting=True)
    assert confirmed.status_code == 200
    token = await _order_token(session_pool, "yk-own-2")
    _, letter, _ = await _pay(api_client, monkeypatch, "yk-own-2")
    await _store_subscription(session_pool, "owner@mail.ru")

    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("yk-own-2")
        owner = await Repository(session).get_user_by_telegram_id(owner_id)
        assert payment.user_id == owner.id
    # Письмо уходит владельцу почты, но без пароля — пароль у аккаунта свой.
    assert letter.await_args.args[0] == "owner@mail.ru"
    assert letter.await_args.kwargs["temporary_password"] is None
    assert await _login(api_client, "owner@mail.ru", "owner-pass1") == 200
    # Тот, кто платил, мог и не быть владельцем: ссылки на странице нет.
    order = (await api_client.get(f"/web/order/{token}")).json()
    assert order["subscription"]["subscriptionUrl"] is None
    assert order["account"] == {"email": "owner@mail.ru", "isNew": False, "canSetPassword": False}
    denied = await api_client.post(f"/web/order/{token}/password", json={"password": "stolen-pass1"})
    assert denied.status_code == 409


@pytest.mark.asyncio
async def test_an_abandoned_old_style_guest_is_not_an_account(api_client, session_pool, monkeypatch):  # noqa: F811
    async with session_pool() as session:
        repo = Repository(session)
        guest = await repo.create_user(telegram_id=-4242)
        await repo.update_user(guest.id, email="guest@mail.ru")

    response, _ = await _checkout(api_client, monkeypatch, "guest@mail.ru", "yk-guest-1")
    assert response.status_code == 200
    _, letter, _ = await _pay(api_client, monkeypatch, "yk-guest-1")

    # Пустой аккаунт старого образца занят, второй на той же почте не появился.
    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("yk-guest-1")
        assert payment.user_id == guest.id
    assert letter.await_args.kwargs["temporary_password"]


@pytest.mark.asyncio
async def test_registration_waits_while_a_checkout_on_that_address_may_pay(api_client, monkeypatch):  # noqa: F811
    from services import yookassa

    await _checkout(api_client, monkeypatch, "race@mail.ru", "yk-race-1")
    monkeypatch.setattr(yookassa, "get_payment", AsyncMock(return_value={"status": "pending"}))
    blocked = await api_client.post("/web/auth/register", json={"email": "race@mail.ru", "password": "attacker1"})
    assert blocked.status_code == 400 and blocked.json()["detail"] == "payment_in_progress"

    monkeypatch.setattr(yookassa, "get_payment", AsyncMock(return_value={"status": "canceled"}))
    allowed = await api_client.post("/web/auth/register", json={"email": "race@mail.ru", "password": "owner-pass1"})
    assert allowed.status_code == 200


# --- «Забыли пароль?» и смена пароля -----------------------------------------


def _mail_on(monkeypatch):
    from services import web_account_routes

    monkeypatch.setattr(web_account_routes.mailer, "is_configured", lambda: True)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(web_account_routes.web_delivery, "send_reset_letter", sent)
    return sent


@pytest.mark.asyncio
async def test_forgot_password_mails_a_one_time_link(api_client, monkeypatch):  # noqa: F811
    await api_client.post("/web/auth/register", json={"email": "forgot@mail.ru", "password": "old-pass-1"})
    sent = _mail_on(monkeypatch)

    response = await api_client.post("/web/auth/forgot", json={"email": " Forgot@Mail.ru "})

    assert response.json() == {"ok": True}
    email, token = sent.await_args.args
    assert email == "forgot@mail.ru"
    reset = await api_client.post("/web/auth/reset", json={"token": token, "password": "new-pass-12"})
    assert reset.status_code == 200 and reset.json()["telegramId"] < 0
    assert await _login(api_client, "forgot@mail.ru", "new-pass-12") == 200
    assert await _login(api_client, "forgot@mail.ru", "old-pass-1") == 401

    reused = await api_client.post("/web/auth/reset", json={"token": token, "password": "other-pass-1"})
    assert reused.status_code == 400 and reused.json()["detail"] == "invalid_token"


@pytest.mark.asyncio
async def test_forgot_password_answers_the_same_for_an_unknown_address(api_client, monkeypatch):  # noqa: F811
    sent = _mail_on(monkeypatch)

    response = await api_client.post("/web/auth/forgot", json={"email": "nobody@mail.ru"})

    assert response.json() == {"ok": True}
    sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_forgot_password_says_so_when_mail_is_down(api_client, monkeypatch):  # noqa: F811
    from services import web_account_routes

    monkeypatch.setattr(web_account_routes.mailer, "is_configured", lambda: False)
    response = await api_client.post("/web/auth/forgot", json={"email": "any@mail.ru"})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_a_reset_link_lives_one_hour(session_pool):
    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=-5151)
        await repo.update_user(user.id, email="hour@mail.ru")
        _, token = await web_passwords.issue_reset(session, "hour@mail.ru")
        row = (await session.execute(web_passwords.select(web_passwords.WebPasswordReset))).scalars().one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

        from services.billing_api import WebAuthError

        with pytest.raises(WebAuthError, match="invalid_token"):
            await web_passwords.reset_password(session, token, "new-pass-12")


@pytest.mark.asyncio
async def test_changing_the_password_needs_the_current_one(api_client):  # noqa: F811
    registered = await api_client.post(
        "/web/auth/register", json={"email": "change@mail.ru", "password": "first-pass1"}
    )
    account = registered.json()["telegramId"]

    wrong = await api_client.post(
        "/web/auth/password",
        json={"telegramId": account, "currentPassword": "guess-pass1", "newPassword": "second-pass1"},
    )
    assert wrong.status_code == 403
    ok = await api_client.post(
        "/web/auth/password",
        json={"telegramId": account, "currentPassword": "first-pass1", "newPassword": "second-pass1"},
    )
    assert ok.status_code == 200
    assert await _login(api_client, "change@mail.ru", "second-pass1") == 200


# --- письма ------------------------------------------------------------------


def test_the_letter_links_the_bot_and_carries_the_login_for_a_new_account(monkeypatch):
    monkeypatch.setattr(web_delivery.settings, "WEB_BASE_URL", "https://unlockproject.site")

    _, text, body = web_delivery.build_letter(
        "https://unlockru.site/sub/T", "Standard", None, login_email="a@mail.ru", temporary_password="Abc234xyzQ"
    )

    for part in (text, body):
        assert "https://t.me/unlkvpn_bot" in part
        assert "a@mail.ru" in part and "Abc234xyzQ" in part
        assert "Спам" in part
    assert 'href="https://t.me/unlkvpn_bot"' in body


def test_a_renewal_letter_has_no_password(monkeypatch):
    _, text, body = web_delivery.build_letter("https://unlockru.site/sub/T", "Standard", None)

    assert "пароль" not in text.lower() and "пароль" not in body.lower()
    assert "https://t.me/unlkvpn_bot" in text


def test_the_reset_link_keeps_the_token_out_of_server_logs(monkeypatch):
    monkeypatch.setattr(web_delivery.settings, "WEB_BASE_URL", "https://unlockproject.site")

    assert web_delivery.reset_url("tok_en") == "https://unlockproject.site/cabinet/reset#t=tok_en"
    _, text, body = web_delivery.build_reset_letter("https://unlockproject.site/cabinet/reset#t=x")
    assert "cabinet/reset#t=x" in text and "cabinet/reset#t=x" in body


def test_a_temporary_password_passes_the_password_rules():
    assert webauth.is_password_acceptable(web_checkout.temporary_password())


@pytest.mark.asyncio
async def test_a_failed_delivery_can_be_retried_by_yookassa(api_client, monkeypatch):  # noqa: F811
    from services import http_api as api_mod

    class _Redis:
        def __init__(self):
            self.store = {}

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in self.store:
                return None
            self.store[key] = value
            return True

        async def delete(self, key):
            self.store.pop(key, None)

    redis = _Redis()
    api_client._transport.app.state.redis = redis
    await _checkout(api_client, monkeypatch, "retry@mail.ru", "yk-retry-1")
    monkeypatch.setattr(api_mod.email_orders, "fulfill", AsyncMock(side_effect=RuntimeError("db down")))

    response, _, _ = await _pay(api_client, monkeypatch, "yk-retry-1")

    assert response.status_code == 500
    # Отметки о дубле нет — повтор вебхука будет обработан, а не отброшен.
    assert "yookassa:evt:yk-retry-1" not in redis.store


# --- аудит 22.09.2026: SEC-03 и SEC-05 -------------------------------------------


@pytest.mark.asyncio
async def test_a_receipt_email_on_a_telegram_account_does_not_capture_a_purchase(api_client, session_pool, monkeypatch):  # noqa: F811
    """Почту для чеков человек вписывает в боте сам, без подтверждения. Вписав
    чужой адрес, он не должен получать чужие оплаты по этой почте."""
    async with session_pool() as session:
        repo = Repository(session)
        squatter = await repo.create_user(telegram_id=777001)
        await repo.update_user(squatter.id, email="victim@mail.ru")

    response, _ = await _checkout(api_client, monkeypatch, "victim@mail.ru", "yk-sq-1")
    assert response.status_code == 200, "это не «аккаунт уже есть» — у почты нет аккаунта сайта"
    await _pay(api_client, monkeypatch, "yk-sq-1")

    async with session_pool() as session:
        payment = await Repository(session).get_payment_by_external_id("yk-sq-1")
        owner = await Repository(session).get_user(payment.user_id)
    assert owner.telegram_id < 0 and owner.id != squatter.id


@pytest.mark.asyncio
async def test_login_by_email_finds_the_site_account_first(api_client, session_pool):  # noqa: F811
    from services import webauth

    async with session_pool() as session:
        repo = Repository(session)
        older = await repo.create_user(telegram_id=777002)
        await repo.update_user(older.id, email="shared@mail.ru", web_password_hash=webauth.hash_password("tg-pass-11"))
        site = await repo.create_user(telegram_id=-777002)
        await repo.update_user(site.id, email="shared@mail.ru", web_password_hash=webauth.hash_password("site-pass-1"))

    ok = await api_client.post("/web/auth/login", json={"email": "shared@mail.ru", "password": "site-pass-1"})
    assert ok.status_code == 200 and ok.json()["telegramId"] == -777002


@pytest.mark.asyncio
async def test_a_telegram_account_with_its_own_site_password_still_logs_in(api_client, session_pool):  # noqa: F811
    from services import webauth

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=777003)
        await repo.update_user(user.id, email="solo@mail.ru", web_password_hash=webauth.hash_password("solo-pass-1"))

    ok = await api_client.post("/web/auth/login", json={"email": "solo@mail.ru", "password": "solo-pass-1"})
    assert ok.status_code == 200 and ok.json()["telegramId"] == 777003


@pytest.mark.asyncio
async def test_the_yookassa_payment_id_cannot_set_the_password(api_client, session_pool, monkeypatch):  # noqa: F811
    """Номер платежа ЮKassa виден в квитанциях и переписке; пароль задаётся только
    по номеру заказа из адреса возврата, который есть лишь у браузера покупателя."""
    await _checkout(api_client, monkeypatch, "pid@mail.ru", "yk-pid-1")
    await _pay(api_client, monkeypatch, "yk-pid-1")

    by_payment = await api_client.get("/web/order/yk-pid-1")
    assert by_payment.json()["account"]["canSetPassword"] is False
    denied = await api_client.post("/web/order/yk-pid-1/password", json={"password": "stolen-pass1"})
    assert denied.status_code == 409

    token = await _order_token(session_pool, "yk-pid-1")
    assert (await api_client.post(f"/web/order/{token}/password", json={"password": "own-pass-12"})).status_code == 200


def test_the_link_notice_names_the_telegram_account_and_support():
    _, text, body = web_delivery.build_link_notice("new_owner")
    for part in (text, body):
        assert "@new_owner" in part and "unlock_support_bot" in part
