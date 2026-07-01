from unittest.mock import AsyncMock, Mock

from bot import banners
from bot.banners import CABINET_BANNER, WELCOME_BANNER, pick_start_banner, send_banner


def test_pick_start_banner_new_user_gets_welcome():
    assert pick_start_banner(is_new_user=True) == WELCOME_BANNER


def test_pick_start_banner_returning_user_gets_cabinet():
    assert pick_start_banner(is_new_user=False) == CABINET_BANNER


async def test_send_banner_uploads_then_reuses_file_id(fake_bot, monkeypatch):
    monkeypatch.setattr(banners, "_file_ids", {})
    sent = Mock()
    sent.photo = [Mock(file_id="FID123")]
    fake_bot.send_photo = AsyncMock(return_value=sent)

    await send_banner(fake_bot, 42, "assets/x.jpg", "hello")
    assert banners._file_ids["assets/x.jpg"] == "FID123"

    await send_banner(fake_bot, 42, "assets/x.jpg", "hello again")
    # Second call reuses the cached file_id instead of re-uploading the file.
    assert fake_bot.send_photo.await_args.args[1] == "FID123"


async def test_send_banner_falls_back_to_text_when_photo_fails(fake_bot, monkeypatch):
    monkeypatch.setattr(banners, "_file_ids", {})
    fake_bot.send_photo = AsyncMock(side_effect=FileNotFoundError("missing asset"))

    await send_banner(fake_bot, 42, "assets/missing.jpg", "caption text")

    fake_bot.send_photo.assert_awaited_once()
    fake_bot.send_message.assert_awaited_once()
    assert fake_bot.send_message.await_args.args[1] == "caption text"
    # A broken banner must not cache a file_id.
    assert "assets/missing.jpg" not in banners._file_ids
