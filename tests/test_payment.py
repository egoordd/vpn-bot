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
