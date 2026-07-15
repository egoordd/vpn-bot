import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts import receipts_job


class _FakeResponse:
    def __init__(self, status: int = 200, payload: dict | None = None):
        self.status = status
        self._payload = payload or {}

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, pending: dict, complete: dict | None = None):
        self._pending = pending
        self._complete = complete or {"ok": True, "deliveredTelegram": True, "deliveredEmail": False}
        self.completed_posts: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        return _FakeResponse(200, self._pending)

    def post(self, url, json=None, **kwargs):
        self.completed_posts.append((url, json))
        return _FakeResponse(200, self._complete)


@pytest.fixture(autouse=True)
def _job_env(monkeypatch, tmp_path):
    monkeypatch.setattr(receipts_job, "LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(
        receipts_job.settings,
        "BILLING_API_TOKEN",
        type(receipts_job.settings.BILLING_API_TOKEN)("test-token"),
    )


@pytest.mark.unit
def test_ledger_roundtrip(tmp_path):
    path = tmp_path / "sub" / "ledger.json"
    assert receipts_job.load_ledger(path) == {}
    receipts_job.save_ledger({"11": "https://lknpd.nalog.ru/r/1"}, path)
    assert receipts_job.load_ledger(path) == {"11": "https://lknpd.nalog.ru/r/1"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_registers_income_and_posts_back(monkeypatch):
    create = AsyncMock(return_value="https://lknpd.nalog.ru/api/v1/receipt/inn/u1/print")
    monkeypatch.setattr(receipts_job.moynalog, "create_income", create)

    session = _FakeSession(
        {"items": [{"paymentId": 11, "amountKopecks": 14900, "serviceName": "Оплата подписки: 1 месяц"}]}
    )
    done = await receipts_job.run(session)

    assert done == 1
    create.assert_awaited_once_with(14900, name="Оплата подписки: 1 месяц")
    (url, body), = session.completed_posts
    assert url.endswith("/web/receipts/11/complete")
    assert body == {"receiptUrl": "https://lknpd.nalog.ru/api/v1/receipt/inn/u1/print"}
    # income is in the ledger for replay safety
    assert receipts_job.load_ledger()["11"] == "https://lknpd.nalog.ru/api/v1/receipt/inn/u1/print"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_replays_ledger_instead_of_duplicating_income(monkeypatch):
    # A previous run registered the income but failed to POST it back.
    receipts_job.save_ledger({"11": "https://lknpd.nalog.ru/r/old"})
    create = AsyncMock()
    monkeypatch.setattr(receipts_job.moynalog, "create_income", create)

    session = _FakeSession({"items": [{"paymentId": 11, "amountKopecks": 14900, "serviceName": "x"}]})
    done = await receipts_job.run(session)

    assert done == 1
    create.assert_not_awaited()  # no duplicate ФНС income
    (_, body), = session.completed_posts
    assert body == {"receiptUrl": "https://lknpd.nalog.ru/r/old"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_no_pending_is_noop(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(receipts_job.moynalog, "create_income", create)

    session = _FakeSession({"items": []})
    assert await receipts_job.run(session) == 0
    create.assert_not_awaited()
    assert session.completed_posts == []
