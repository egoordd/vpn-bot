import re

import pytest

from services import payment
from services.payment import (
    PLANS,
    create_invoice_payload,
    normalize_payment_plan_code,
    parse_invoice_payload,
    parse_invoice_payload_details,
)


@pytest.mark.unit
def test_plans_shape():
    assert set(PLANS) == {
        "standard_1m",
        "standard_3m",
        "standard_6m",
        "standard_12m",
    }
    for plan in PLANS.values():
        assert {"days", "rub_amount", "crypto_amount"} <= set(plan)


@pytest.mark.unit
def test_create_invoice_payload_format():
    payload = create_invoice_payload(42, "standard_1m")
    assert re.match(r"^unlock:42:standard_1m:[0-9a-f]{32}$", payload)


@pytest.mark.unit
def test_create_invoice_payload_unknown_plan():
    with pytest.raises(ValueError):
        create_invoice_payload(42, "bad")


@pytest.mark.unit
def test_create_invoice_payload_requires_premium_region():
    with pytest.raises(ValueError):
        create_invoice_payload(42, "premium_1m")

    with pytest.raises(ValueError):
        create_invoice_payload(42, "standard_1m", region="ams")


@pytest.mark.unit
def test_parse_invoice_payload_round_trip():
    payload = create_invoice_payload(777, "standard_3m")
    assert parse_invoice_payload(payload) == (777, "standard_3m")




@pytest.mark.unit
def test_legacy_payment_plan_aliases_normalize():
    assert normalize_payment_plan_code("1m") == "standard_1m"
    assert parse_invoice_payload("unlock:777:1m:abc") == (777, "standard_1m")


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        "wrong:1:1m:abc",
        "unlock:1:1m",
        "unlock:1:bad:abc",
        "unlock:not-int:1m:abc",
        "unlock:1:trial:abc",
        "unlock:1:premium_1m:bad:abc",
    ],
)
def test_parse_invoice_payload_invalid(payload):
    with pytest.raises(ValueError):
        parse_invoice_payload(payload)


def test_create_topup_payload_format_and_parse_roundtrip():
    payload = payment.create_topup_payload(42, 15000)

    parts = payload.split(":")
    assert parts[0] == "unlock_topup"
    assert parts[1] == "42"
    assert parts[2] == "15000"
    assert len(parts[3]) == 32

    parsed = payment.parse_topup_payload(payload)
    assert parsed == payment.ParsedTopupPayload(user_id=42, amount_kopecks=15000)


def test_create_topup_payload_rejects_out_of_range():
    with pytest.raises(ValueError):
        payment.create_topup_payload(1, payment.MIN_TOPUP_KOPECKS - 1)
    with pytest.raises(ValueError):
        payment.create_topup_payload(1, payment.MAX_TOPUP_KOPECKS + 1)


def test_parse_topup_payload_returns_none_for_plan_payloads():
    plan_payload = payment.create_invoice_payload(user_id=1, plan="standard_1m")
    assert payment.parse_topup_payload(plan_payload) is None


@pytest.mark.parametrize(
    "payload",
    [
        "unlock_topup:1:100",
        "unlock_topup:abc:100:deadbeef",
        "unlock_topup:1:zero:deadbeef",
        "unlock_topup:1:-5:deadbeef",
    ],
)
def test_parse_topup_payload_invalid(payload):
    with pytest.raises(ValueError):
        payment.parse_topup_payload(payload)


def test_usdt_amount_for_kopecks_rounds_up():
    from decimal import Decimal

    assert payment.usdt_amount_for_kopecks(15000, Decimal("90")) == "1.67"
    assert payment.usdt_amount_for_kopecks(30000, Decimal("90")) == "3.34"
    assert payment.usdt_amount_for_kopecks(9000, Decimal("90")) == "1.00"
    with pytest.raises(ValueError):
        payment.usdt_amount_for_kopecks(15000, Decimal("0"))


@pytest.mark.unit
def test_parse_invoice_payload_keeps_reading_old_region_payloads():
    """Счёт, выписанный до удаления Premium, должен остаться оплачиваемым.

    Пятая часть несла регион. Создавать такие больше нельзя, но человек,
    открывший счёт до правки, не должен упереться в ошибку разбора — регион
    просто отбрасывается.
    """
    details = parse_invoice_payload_details("unlock:1:standard_1m:ams:abc")

    assert details.user_id == 1
    assert details.plan == "standard_1m"
    assert details.region is None
