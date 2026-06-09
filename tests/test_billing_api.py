import re

import pytest

from database.repository import Repository
from services.billing_api import (
    activate_access,
    attach_referral_code,
    build_payment_intent,
    crypto_minor_units,
    get_account_overview,
    get_billing_plan,
    get_referral_overview,
    get_subscription_snapshot,
    get_wallet,
    list_billing_plans,
    list_billing_regions,
    preview_checkout_discount,
    redeem_balance_promo,
    register_cryptobot_payment,
    reward_referral_for_payment,
)
from services import promo as promo_service
from services import wallet as wallet_service
from services.panel_gateway import PanelAccount, PanelUserNotFoundError
from services.tariffs import BYTES_IN_GB


class FakeBillingPanelGateway:
    provider = "fake"

    def __init__(self):
        self.created: list[dict[str, object]] = []

    def build_username(self, telegram_id: int) -> str:
        return f"fake_{telegram_id}"

    async def get_user(self, username: str) -> PanelAccount:
        raise PanelUserNotFoundError(username)

    async def create_user(self, **kwargs) -> PanelAccount:
        self.created.append(kwargs)
        username = str(kwargs["username"])
        return PanelAccount(
            username=username,
            short_uuid=f"short-{username}",
            subscription_url=f"https://sub.example/{username}",
            status="active",
            expire_at=1783036800,
            traffic_limit_bytes=10 * BYTES_IN_GB,
            used_traffic_bytes=123,
            lifetime_used_traffic_bytes=123,
            device_limit=1,
            provider=self.provider,
        )

    async def modify_user(self, **kwargs) -> PanelAccount:
        raise AssertionError("modify_user should not be called in this test")


@pytest.mark.unit
def test_list_billing_plans_excludes_trial_by_default():
    plans = list_billing_plans()

    assert "trial" not in {plan.code for plan in plans}
    assert [plan.code for plan in plans[:2]] == ["standard_1m", "standard_3m"]
    assert all(plan.price_rub > 0 for plan in plans)


@pytest.mark.unit
def test_list_billing_plans_filters_and_can_include_trial():
    premium = list_billing_plans(tier="premium")
    with_trial = list_billing_plans(include_trial=True)

    assert {plan.tier for plan in premium} == {"premium"}
    assert [plan.code for plan in premium] == [
        "premium_1m",
        "premium_3m",
        "premium_6m",
        "premium_12m",
    ]
    assert with_trial[0].code == "trial"


@pytest.mark.unit
def test_get_billing_plan_normalizes_legacy_alias():
    plan = get_billing_plan("1m")

    assert plan.code == "standard_1m"
    assert plan.title == "Standard 1 месяц"


@pytest.mark.unit
def test_list_billing_regions_returns_premium_region_dto():
    regions = {region.code: region for region in list_billing_regions()}

    assert regions["ams"].country_code == "NL"
    assert regions["waw"].is_on_demand is True


@pytest.mark.unit
def test_crypto_minor_units_rounds_half_up():
    assert crypto_minor_units("1.995") == 200
    assert crypto_minor_units("1.994") == 199


@pytest.mark.integration
async def test_build_payment_intent_creates_user_and_standard_payload(db_session):
    intent = await build_payment_intent(
        db_session,
        telegram_id=1101,
        username="alice",
        plan="1m",
    )

    repo = Repository(db_session)
    user = await repo.get_user_by_telegram_id(1101)

    assert user is not None
    assert user.id == intent.user_id
    assert intent.plan.code == "standard_1m"
    assert intent.region is None
    assert intent.amount == "1.99"
    assert intent.amount_minor == 199
    assert intent.asset == "USDT"
    assert intent.description == "Общий тариф на 30 дней"
    assert re.match(rf"^unlock:{user.id}:standard_1m:[0-9a-f]{{32}}$", intent.payload)


@pytest.mark.integration
async def test_build_payment_intent_requires_valid_premium_region(db_session):
    with pytest.raises(ValueError):
        await build_payment_intent(
            db_session,
            telegram_id=1102,
            username=None,
            plan="premium_1m",
        )

    with pytest.raises(ValueError):
        await build_payment_intent(
            db_session,
            telegram_id=1102,
            username=None,
            plan="standard_1m",
            region="ams",
        )


@pytest.mark.integration
async def test_build_payment_intent_adds_premium_region_to_payload(db_session):
    intent = await build_payment_intent(
        db_session,
        telegram_id=1103,
        username="premium",
        plan="premium_1m",
        region="AMS",
    )

    assert intent.plan.code == "premium_1m"
    assert intent.region is not None
    assert intent.region.code == "ams"
    assert intent.amount == "4.99"
    assert intent.amount_minor == 499
    assert "Нидерланды" in intent.description
    assert re.match(rf"^unlock:{intent.user_id}:premium_1m:ams:[0-9a-f]{{32}}$", intent.payload)


@pytest.mark.integration
async def test_register_cryptobot_payment_persists_pending_invoice(db_session):
    intent = await build_payment_intent(
        db_session,
        telegram_id=1104,
        username="buyer",
        plan="standard_3m",
    )

    payment = await register_cryptobot_payment(db_session, intent=intent, external_invoice_id="invoice-1104")

    repo = Repository(db_session)
    stored = await repo.get_payment_by_external_id("invoice-1104")
    assert stored == payment
    assert stored is not None
    assert stored.user_id == intent.user_id
    assert stored.amount == 499
    assert stored.invoice_payload == intent.payload
    assert stored.status == "pending"


@pytest.mark.integration
async def test_subscription_snapshot_and_activate_access(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=1105)

    empty = await get_subscription_snapshot(db_session, user.id)
    assert empty.exists is False
    assert empty.is_active is False

    gateway = FakeBillingPanelGateway()
    snapshot = await activate_access(db_session, user.id, "trial", panel_gateway=gateway)

    assert gateway.created[0]["username"] == "fake_1105"
    assert snapshot.exists is True
    assert snapshot.is_active is True
    assert snapshot.plan == "trial"
    assert snapshot.tier == "trial"
    assert snapshot.subscription_url == "https://sub.example/fake_1105"
    assert snapshot.traffic_used_bytes == 123


@pytest.mark.integration
async def test_get_account_overview_composes_subscription_wallet_referral(db_session):
    repo = Repository(db_session)
    referrer = await repo.create_user(telegram_id=1201)
    user = await repo.create_user(telegram_id=1202)
    await attach_referral_code(db_session, user_id=user.id, ref_code=referrer.ref_code)
    await wallet_service.deposit(db_session, user.id, 5000)

    overview = await get_account_overview(db_session, user.id)

    assert overview.user_id == user.id
    assert overview.telegram_id == 1202
    assert overview.subscription.exists is False
    assert overview.wallet.balance_kopecks == 5000
    assert overview.balance_display == "50₽"
    assert overview.referral.ref_code == user.ref_code
    assert overview.referral.referrals_count == 0


@pytest.mark.integration
async def test_get_account_overview_unknown_user_raises(db_session):
    with pytest.raises(ValueError):
        await get_account_overview(db_session, 999999)


@pytest.mark.integration
async def test_get_wallet_wrapper_returns_snapshot(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=1203)
    await wallet_service.deposit(db_session, user.id, 1200)

    snapshot = await get_wallet(db_session, user.id)

    assert snapshot.balance_kopecks == 1200


@pytest.mark.integration
async def test_redeem_balance_promo_and_preview_discount_via_facade(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=1204)
    await repo.create_promo_code(code="WELCOME", kind=promo_service.PROMO_BALANCE_BONUS, value=3000)
    await repo.create_promo_code(code="SALE", kind=promo_service.PROMO_PERCENT_DISCOUNT, value=25)

    redemption = await redeem_balance_promo(db_session, user_id=user.id, code="WELCOME")
    assert redemption.credited_kopecks == 3000
    assert await wallet_service.get_balance(db_session, user.id) == 3000

    discount = await preview_checkout_discount(
        db_session, user_id=user.id, code="SALE", amount_kopecks=20000
    )
    assert discount.final_kopecks == 15000


@pytest.mark.integration
async def test_referral_overview_and_reward_via_facade(db_session):
    repo = Repository(db_session)
    referrer = await repo.create_user(telegram_id=1205)
    referee = await repo.create_user(telegram_id=1206)
    await attach_referral_code(db_session, user_id=referee.id, ref_code=referrer.ref_code)

    entry = await reward_referral_for_payment(
        db_session, paid_user_id=referee.id, plan_code="standard_1m", payment_reference="pay-f1"
    )
    assert entry is not None

    stats = await get_referral_overview(db_session, referrer.id)
    assert stats.referrals_count == 1
    assert stats.total_earned_kopecks == 2980
