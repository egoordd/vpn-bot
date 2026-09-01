import re

import pytest

from database.repository import Repository
from services.billing_api import (
    activate_access,
    attach_referral_code,
    build_payment_intent,
    get_account_overview,
    get_billing_plan,
    get_referral_overview,
    get_subscription_snapshot,
    list_billing_plans,
        preview_checkout_discount,
)
from services import promo as promo_service
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
    standard = list_billing_plans(tier="standard")
    with_trial = list_billing_plans(include_trial=True)

    assert {plan.tier for plan in standard} == {"standard"}
    assert [plan.code for plan in standard] == [
        "standard_1m",
        "standard_3m",
        "standard_6m",
        "standard_12m",
    ]
    assert with_trial[0].code == "trial"


@pytest.mark.unit
def test_get_billing_plan_normalizes_legacy_alias():
    plan = get_billing_plan("1m")

    assert plan.code == "standard_1m"
    assert plan.title == "Standard 1 месяц"



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
    assert intent.description == "Общий тариф на 30 дней, 150 ГБ в месяц"
    assert re.match(rf"^unlock:{user.id}:standard_1m:[0-9a-f]{{32}}$", intent.payload)



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
async def test_get_account_overview_composes_subscription_and_referral(db_session):
    repo = Repository(db_session)
    referrer = await repo.create_user(telegram_id=1201)
    user = await repo.create_user(telegram_id=1202)
    await attach_referral_code(db_session, user_id=user.id, ref_code=referrer.ref_code)

    overview = await get_account_overview(db_session, user.id)

    assert overview.user_id == user.id
    assert overview.telegram_id == 1202
    assert overview.subscription.exists is False
    assert overview.referral.ref_code == user.ref_code
    assert overview.referral.referrals_count == 0


@pytest.mark.integration
async def test_get_account_overview_unknown_user_raises(db_session):
    with pytest.raises(ValueError):
        await get_account_overview(db_session, 999999)

@pytest.mark.integration
async def test_preview_discount_via_facade(db_session):
    repo = Repository(db_session)
    user = await repo.create_user(telegram_id=1204)
    await repo.create_promo_code(code="SALE", kind=promo_service.PROMO_PERCENT_DISCOUNT, value=25)

    discount = await preview_checkout_discount(
        db_session, user_id=user.id, code="SALE", amount_kopecks=20000
    )
    assert discount.final_kopecks == 15000

@pytest.mark.integration
async def test_referral_overview_counts_who_was_brought_in(db_session):
    repo = Repository(db_session)
    referrer = await repo.create_user(telegram_id=1205)
    referee = await repo.create_user(telegram_id=1206)
    await attach_referral_code(db_session, user_id=referee.id, ref_code=referrer.ref_code)

    stats = await get_referral_overview(db_session, referrer.id)

    assert stats.referrals_count == 1
    assert stats.ref_code == referrer.ref_code


# --- paying for an account you cannot reach through Telegram -------------------

def test_subscription_token_reads_the_account_out_of_a_link():
    """When a subscription lapses the VPN stops, and without it Telegram does not
    open in Russia — so the bot is unreachable exactly when someone wants to pay.
    The link is still in their app, and it names the account."""
    from services.billing_api import subscription_token

    token = "dGdfNzQwNDg0MzI0LDE3ODU3NDI1MjgPrVeO5tzmi"
    assert subscription_token(f"https://sub.unlockvpn.site/sub/{token}") == "tg_740484324"
    assert subscription_token(f"https://sub.unlockvpn.site/sub/{token}/auto") == "tg_740484324"
    assert subscription_token(f"  {token}  ") == "tg_740484324"


def test_subscription_token_rejects_anything_that_is_not_ours():
    """It selects an account to credit, so a loose parse would let one customer
    top up another's subscription."""
    from services.billing_api import subscription_token

    assert subscription_token("https://gl.molniya.sbs/sub/xBUbYpm0gyVft6BHoXPJzvBAJ") is None
    assert subscription_token("hello world") is None
    assert subscription_token("") is None
    assert subscription_token(None) is None
    assert subscription_token("x" * 900) is None


def test_subscription_token_handles_web_only_accounts():
    """Email buyers carry a synthetic negative id; their links must parse too."""
    from services.billing_api import subscription_token
    import base64

    token = base64.b64encode(b"tg_-2499639603645,1785").decode()
    assert subscription_token(token) == "tg_-2499639603645"


@pytest.mark.asyncio
async def test_paying_with_a_link_tops_up_the_account_that_owns_it(db_session):
    """The whole point of the link path: a customer whose subscription lapsed
    cannot open Telegram in Russia, so the site must credit the account they
    already have rather than quietly starting a second one beside it."""
    import base64
    from datetime import datetime, timedelta, timezone

    from database.repository import Repository
    from services.billing_api import build_web_payment_intent

    repo = Repository(db_session)
    owner = await repo.get_or_create_user(telegram_id=7404, username="marina")
    await repo.create_subscription(
        user_id=owner.id,
        plan="standard_1m",
        started_at=datetime.now(timezone.utc) - timedelta(days=32),
        expires_at=datetime.now(timezone.utc) - timedelta(days=2),  # already lapsed
        sub_token="tg_7404",
    )
    link = "https://sub.unlockvpn.site/sub/" + base64.b64encode(b"tg_7404,1785").decode()

    intent = await build_web_payment_intent(db_session, plan="1m", subscription_link=link)

    assert intent.user_id == owner.id, "payment must credit the existing account"


@pytest.mark.asyncio
async def test_an_unknown_link_is_refused_rather_than_silently_creating_an_account(db_session):
    """Failing loudly here is the point: a typo that quietly opened a second
    account would take the customer's money and leave their VPN dead."""
    import base64

    from services.billing_api import build_web_payment_intent

    link = "https://sub.unlockvpn.site/sub/" + base64.b64encode(b"tg_999999,1785").decode()
    with pytest.raises(ValueError, match="unknown_subscription"):
        await build_web_payment_intent(db_session, plan="1m", subscription_link=link)
