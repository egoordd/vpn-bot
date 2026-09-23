"""Несколько подписок на одном аккаунте: «ещё одна» и продление каждой отдельно."""

from datetime import datetime, timedelta, timezone

import pytest

from database.repository import Repository
from services import subscription_slots
from services.panel_gateway import PanelAccount, PanelUserNotFoundError
from services.payment import create_invoice_payload, parse_invoice_payload_details
from services.subscription import _aware, activate_panel_subscription
from tests.test_http_api import api_client  # noqa: F401 - fixture


class SlotPanel:
    """Панель, которая помнит каждого пользователя отдельно."""

    provider = "marzban"

    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.created: list[str] = []

    def build_username(self, telegram_id: int) -> str:
        return f"tg_{telegram_id}"

    async def get_user(self, username: str) -> PanelAccount:
        if username not in self.users:
            raise PanelUserNotFoundError(username)
        return self._account(username)

    async def create_user(self, **kwargs) -> PanelAccount:
        self.users[kwargs["username"]] = kwargs
        self.created.append(kwargs["username"])
        return self._account(kwargs["username"])

    async def modify_user(self, **kwargs) -> PanelAccount:
        self.users[kwargs["username"]] = {**self.users.get(kwargs["username"], {}), **kwargs}
        return self._account(kwargs["username"])

    async def reset_traffic(self, username: str) -> PanelAccount:
        return self._account(username)

    def _account(self, username: str) -> PanelAccount:
        return PanelAccount(
            username=username,
            short_uuid=f"tok-{username}",
            subscription_url=f"https://panel.example/sub/tok-{username}",
            status="active",
            expire_at=None,
            traffic_limit_bytes=None,
            used_traffic_bytes=0,
            lifetime_used_traffic_bytes=0,
            provider=self.provider,
        )


async def _user_with_paid(session, telegram_id: int, panel: SlotPanel):
    repo = Repository(session)
    user = await repo.create_user(telegram_id=telegram_id)
    await activate_panel_subscription(session, user.id, "standard_1m", panel_gateway=panel)
    return repo, user


@pytest.mark.integration
async def test_another_subscription_gets_its_own_link_and_devices(db_session):
    panel = SlotPanel()
    repo, user = await _user_with_paid(db_session, 7101, panel)

    extra = await activate_panel_subscription(
        db_session, user.id, "standard_1m", panel_gateway=panel, target="new"
    )

    active = await repo.list_active_subscriptions(user.id)
    assert extra.panel_username == "tg_7101_s2"
    assert panel.created == ["tg_7101", "tg_7101_s2"]
    assert len(active) == 2, "первая подписка не должна гаснуть"
    assert {row.device_limit for row in active} == {3}
    assert extra.subscription_url != next(r for r in active if r.id != extra.id).subscription_url


@pytest.mark.integration
async def test_another_subscription_starts_now(db_session):
    panel = SlotPanel()
    _, user = await _user_with_paid(db_session, 7102, panel)
    before = datetime.now(timezone.utc)

    extra = await activate_panel_subscription(
        db_session, user.id, "standard_1m", panel_gateway=panel, target="new"
    )

    assert abs((_aware(extra.started_at) - before).total_seconds()) < 60
    assert (_aware(extra.expires_at) - before).days in (29, 30)


@pytest.mark.integration
async def test_ordinary_purchase_extends_the_main_one_and_leaves_the_extra(db_session):
    panel = SlotPanel()
    repo, user = await _user_with_paid(db_session, 7103, panel)
    extra = await activate_panel_subscription(
        db_session, user.id, "standard_1m", panel_gateway=panel, target="new"
    )
    main_before = next(r for r in await repo.list_active_subscriptions(user.id) if r.id != extra.id)

    renewed = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=panel)

    active = await repo.list_active_subscriptions(user.id)
    assert renewed.panel_username == "tg_7103"
    assert _aware(renewed.started_at) == _aware(main_before.expires_at)
    assert {row.panel_username for row in active} == {"tg_7103", "tg_7103_s2"}


@pytest.mark.integration
async def test_renewing_the_extra_extends_only_it(db_session):
    panel = SlotPanel()
    repo, user = await _user_with_paid(db_session, 7104, panel)
    extra = await activate_panel_subscription(
        db_session, user.id, "standard_1m", panel_gateway=panel, target="new"
    )
    main = next(r for r in await repo.list_active_subscriptions(user.id) if r.id != extra.id)

    renewed = await activate_panel_subscription(
        db_session, user.id, "standard_3m", panel_gateway=panel, target=str(extra.id)
    )

    active = {row.panel_username: row for row in await repo.list_active_subscriptions(user.id)}
    assert renewed.panel_username == "tg_7104_s2"
    assert _aware(renewed.started_at) == _aware(extra.expires_at)
    assert _aware(active["tg_7104"].expires_at) == _aware(main.expires_at), "основная не тронута"
    assert active["tg_7104_s2"].id == renewed.id


@pytest.mark.integration
async def test_a_foreign_subscription_id_extends_the_buyers_main(db_session):
    """Чужой номер в счёте не должен ни продлить чужое, ни потерять оплату."""
    panel = SlotPanel()
    repo, owner = await _user_with_paid(db_session, 7105, panel)
    foreign = (await repo.list_active_subscriptions(owner.id))[0]
    _, buyer = await _user_with_paid(db_session, 7106, panel)

    renewed = await activate_panel_subscription(
        db_session, buyer.id, "standard_1m", panel_gateway=panel, target=str(foreign.id)
    )

    assert renewed.user_id == buyer.id
    assert renewed.panel_username == "tg_7106"


@pytest.mark.integration
async def test_slot_numbers_reuse_the_lowest_free_one(db_session):
    panel = SlotPanel()
    repo, user = await _user_with_paid(db_session, 7107, panel)
    for _ in range(3):
        await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=panel, target="new")
    active = await repo.list_active_subscriptions(user.id)
    s3 = next(r for r in active if r.panel_username == "tg_7107_s3")
    s3.is_active = False
    await db_session.commit()

    again = await activate_panel_subscription(db_session, user.id, "standard_1m", panel_gateway=panel, target="new")

    assert again.panel_username == "tg_7107_s3"


@pytest.mark.integration
async def test_a_trial_is_never_an_extra_subscription(db_session):
    panel = SlotPanel()
    _, user = await _user_with_paid(db_session, 7108, panel)
    with pytest.raises(ValueError):
        await activate_panel_subscription(db_session, user.id, "trial", panel_gateway=panel, target="new")


@pytest.mark.unit
def test_the_purchase_target_survives_the_invoice():
    payload = create_invoice_payload(12, "standard_1m", target="new")
    assert parse_invoice_payload_details(payload).target == "new"
    payload = create_invoice_payload(12, "standard_3m", target="345")
    assert parse_invoice_payload_details(payload).target == "345"
    assert parse_invoice_payload_details(create_invoice_payload(12, "standard_1m")).target is None


@pytest.mark.unit
def test_old_invoices_still_read_without_a_target():
    assert parse_invoice_payload_details("unlock:12:standard_1m:abc").target is None
    # Старые счета с регионом Premium: регион отбрасывается, цели нет.
    assert parse_invoice_payload_details("unlock:12:standard_1m:abc:de").target is None


@pytest.mark.unit
def test_plan_and_target_split():
    assert subscription_slots.split_plan_target("standard_1m@new") == ("standard_1m", "new")
    assert subscription_slots.split_plan_target("standard_1m@42") == ("standard_1m", "42")
    assert subscription_slots.split_plan_target("standard_1m") == ("standard_1m", None)
    with pytest.raises(ValueError):
        subscription_slots.split_plan_target("standard_1m@drop table")


@pytest.mark.unit
def test_labels_and_limits():
    class Row:
        def __init__(self, name):
            self.panel_username = name

    rows = [Row("tg_1"), Row("tg_1_s2"), Row("tg_1_s4")]
    assert subscription_slots.free_slot_number(rows) == 3
    assert subscription_slots.label(rows[0]) == "Подписка 1 · основная"
    assert subscription_slots.label(rows[2]) == "Подписка 4"
    assert subscription_slots.can_add(rows)
    assert not subscription_slots.can_add(rows + [Row("tg_1_s3"), Row("tg_1_s5")])
    assert not subscription_slots.can_add([])


@pytest.mark.asyncio
async def test_the_webhook_hands_the_target_to_activation(api_client, session_pool, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from services import http_api as api_mod
    from tests.test_payment_retry import _Redis, _Sub, _yookassa_paid

    async with session_pool() as session:
        repo = Repository(session)
        user = await repo.create_user(telegram_id=880701)
        await repo.create_yookassa_payment(
            user_id=user.id, amount=14900, external_invoice_id="yk-extra-1",
            invoice_payload=create_invoice_payload(user_id=user.id, plan="standard_1m", target="new"),
            plan="standard_1m",
        )
    api_client._transport.app.state.redis = _Redis()
    _yookassa_paid(monkeypatch, api_mod, "yk-extra-1")
    calls = []

    async def activate(**kwargs):
        calls.append(kwargs)
        return _Sub()

    monkeypatch.setattr(api_mod, "activate_panel_subscription", activate)
    monkeypatch.setattr(api_mod.tribute, "deliver_subscription", AsyncMock(return_value=True))

    response = await api_client.post("/yookassa/webhook", json={"object": {"id": "yk-extra-1"}})

    assert response.status_code == 200
    assert calls and calls[0]["target"] == "new"


@pytest.mark.integration
async def test_the_account_info_shows_the_main_subscription(db_session):
    from services.subscription import get_subscription_info

    panel = SlotPanel()
    _, user = await _user_with_paid(db_session, 7111, panel)
    await activate_panel_subscription(db_session, user.id, "standard_12m", panel_gateway=panel, target="new")

    info = await get_subscription_info(db_session, user.id)

    assert info["panel_username"] == "tg_7111"


@pytest.mark.unit
def test_the_gateway_asks_the_limit_for_the_account_not_the_slot(monkeypatch):
    import io
    import json

    from services import sub_gateway

    asked = []

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        asked.append(req.full_url)
        return _Resp(json.dumps({"subscription": {"deviceLimit": 3}}).encode())

    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT_API", "http://api/web/account/by-telegram/{telegram_id}")
    monkeypatch.setattr(sub_gateway.urllib.request, "urlopen", fake_urlopen)
    sub_gateway._PLAN_LIMITS.clear()

    assert sub_gateway.plan_device_limit("tg_555_s2") == 3
    assert asked == ["http://api/web/account/by-telegram/555"]
