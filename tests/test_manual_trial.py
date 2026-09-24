"""Пробник вручную (/trial): для клиентов с Авито и других, кто пришёл не из бота."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import admin
from database.repository import Repository
from services import manual_trial
from tests.test_multi_subscriptions import SlotPanel


@pytest.mark.unit
def test_source_defaults_to_avito_and_rejects_junk():
    assert manual_trial.normalize_source(None) == "avito"
    assert manual_trial.normalize_source("Авито") == "avito"
    assert manual_trial.normalize_source("Youla_2") == "youla_2"
    with pytest.raises(ValueError):
        manual_trial.normalize_source("drop table; --")


@pytest.mark.integration
async def test_trial_is_a_standalone_account_with_the_standard_trial(db_session):
    panel = SlotPanel()

    trial = await manual_trial.issue_manual_trial(db_session, source="avito", panel_gateway=panel)

    assert -(2**52) - 1 <= trial.telegram_id < 0, "no Telegram chat, and outside the mirror range"
    repo = Repository(db_session)
    user = await repo.get_user_by_telegram_id(trial.telegram_id)
    assert user.source == "avito"
    [sub] = await repo.list_active_subscriptions(user.id)
    assert sub.plan == "trial" and sub.device_limit == 2
    assert sub.traffic_limit_bytes == 10 * 1024**3
    assert trial.subscription_url.endswith(f"/sub/tok-tg_{trial.telegram_id}")
    assert panel.created == [f"tg_{trial.telegram_id}"]


@pytest.mark.integration
async def test_each_trial_gets_its_own_account(db_session):
    panel = SlotPanel()
    first = await manual_trial.issue_manual_trial(db_session, panel_gateway=panel)
    second = await manual_trial.issue_manual_trial(db_session, panel_gateway=panel)
    assert first.telegram_id != second.telegram_id
    assert first.subscription_url != second.subscription_url


@pytest.mark.unit
def test_client_text_carries_the_link_and_the_way_to_renew():
    trial = manual_trial.ManualTrial(-5, "avito", "https://unlockru.site/sub/abc", None)
    text = manual_trial.client_message(trial, "27 сентября 2026 года, 18:00 (МСК)")
    assert "https://unlockru.site/sub/abc" in text
    assert "Happ" in text and "/link" in text
    assert text.count("(МСК)") == 1


def _message(user_id: int, text: str):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id, username="x"), text=text, answer=AsyncMock())


@pytest.mark.integration
async def test_trial_command_is_admin_only(session_pool, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    issue = AsyncMock()
    monkeypatch.setattr(admin.manual_trial, "issue_manual_trial", issue)
    message = _message(5, "/trial")

    await admin.manual_trial_handler(message, session_pool)

    issue.assert_not_awaited()
    assert "администраторам" in message.answer.await_args.args[0]


@pytest.mark.integration
async def test_trial_command_sends_the_link_ready_to_forward(session_pool, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    trial = manual_trial.ManualTrial(-77, "avito", "https://unlockru.site/sub/tok", datetime(2026, 9, 27, tzinfo=timezone.utc))
    monkeypatch.setattr(admin.manual_trial, "issue_manual_trial", AsyncMock(return_value=trial))
    message = _message(4, "/trial Авито")

    await admin.manual_trial_handler(message, session_pool)

    first, second = (call.args[0] for call in message.answer.await_args_list)
    assert "avito" in first and "-77" in first
    assert "https://unlockru.site/sub/tok" in second


@pytest.mark.integration
async def test_trial_command_reports_a_panel_failure(session_pool, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    monkeypatch.setattr(admin.manual_trial, "issue_manual_trial", AsyncMock(side_effect=RuntimeError("down")))
    message = _message(4, "/trial")

    await admin.manual_trial_handler(message, session_pool)

    assert "Не удалось" in message.answer.await_args.args[0]


@pytest.mark.integration
async def test_trial_survives_a_session_that_expires_on_commit(session_pool):
    """24.09.2026 a script with SQLAlchemy's default session crashed with
    MissingGreenlet after the trial was already created — reading an expired
    attribute lazily in async code."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    strict = async_sessionmaker(session_pool.kw["bind"], expire_on_commit=True)
    async with strict() as session:
        trial = await manual_trial.issue_manual_trial(session, panel_gateway=SlotPanel())
    assert trial.telegram_id < 0 and trial.expires_at is not None


@pytest.mark.integration
async def test_a_trial_issuer_can_use_trial_but_not_the_rest_of_the_admin(session_pool, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(admin.settings, "ADMIN_IDS", "4")
    monkeypatch.setattr(admin.settings, "TRIAL_ISSUER_IDS", "9, 10")
    trial = manual_trial.ManualTrial(-78, "avito", "https://unlockru.site/sub/t2", datetime(2026, 9, 27, tzinfo=timezone.utc))
    monkeypatch.setattr(admin.manual_trial, "issue_manual_trial", AsyncMock(return_value=trial))

    issuer = _message(10, "/trial")
    await admin.manual_trial_handler(issuer, session_pool)
    assert "https://unlockru.site/sub/t2" in issuer.answer.await_args_list[-1].args[0]

    stats = _message(10, "/stats")
    await admin.admin_help_handler(stats)
    assert "администраторам" in stats.answer.await_args.args[0]
