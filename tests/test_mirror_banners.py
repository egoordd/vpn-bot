"""Баннеры в зеркале: картинка украшает экран, но никогда его не отменяет.

Человек приходит в зеркало, когда основной способ подключения уже не сработал.
Поэтому любая осечка с картинкой обязана заканчиваться обычным текстовым меню,
а не пустотой.
"""

from pathlib import Path

import pytest

from services import mirror_banners, mirror_bot


class FakePhotoApi:
    def __init__(self, *, upload_fails: bool = False):
        self.calls: list[tuple[str, dict]] = []
        self.uploads: list[tuple[dict, Path]] = []
        self.upload_fails = upload_fails

    async def call(self, method, payload=None):
        self.calls.append((method, dict(payload or {})))
        return {}

    async def upload_photo(self, payload, path):
        self.uploads.append((dict(payload), path))
        if self.upload_fails:
            raise FileNotFoundError(path)
        return {"photo": [{"file_id": "small"}, {"file_id": "FILE123"}]}


def _methods(api: FakePhotoApi) -> list[str]:
    return [method for method, _ in api.calls]


@pytest.fixture(autouse=True)
def _forget_uploaded_banners():
    mirror_banners._file_ids.clear()
    yield
    mirror_banners._file_ids.clear()


def test_the_picture_matches_what_the_screen_offers():
    subscriber = mirror_bot.main_menu_keyboard(has_subscription=True, trial_available=False)
    newcomer = mirror_bot.main_menu_keyboard(has_subscription=False, trial_available=True)
    lapsed = mirror_bot.main_menu_keyboard(has_subscription=False, trial_available=False)

    assert mirror_banners.pick(subscriber) == mirror_banners.CABINET
    assert mirror_banners.pick(newcomer) == mirror_banners.WELCOME
    assert mirror_banners.pick(lapsed) == mirror_banners.EXPIRED


def test_every_banner_is_in_the_repository():
    for banner in (mirror_banners.WELCOME, mirror_banners.CABINET, mirror_banners.EXPIRED):
        assert banner.exists(), f"нет файла {banner}"


@pytest.mark.asyncio
async def test_the_picture_is_uploaded_once_and_then_sent_by_id():
    api = FakePhotoApi()
    keyboard = mirror_bot.main_menu_keyboard(has_subscription=False, trial_available=True)

    assert await mirror_banners.send(api, 55, mirror_banners.WELCOME, "меню", keyboard) is True
    assert await mirror_banners.send(api, 55, mirror_banners.WELCOME, "меню", keyboard) is True

    assert len(api.uploads) == 1, "во второй раз картинка не должна ехать заново"
    method, payload = api.calls[-1]
    assert (method, payload["photo"]) == ("sendPhoto", "FILE123")


@pytest.mark.asyncio
async def test_a_broken_picture_still_leaves_the_person_with_a_screen():
    api = FakePhotoApi(upload_fails=True)
    keyboard = mirror_bot.main_menu_keyboard(has_subscription=False, trial_available=True)

    assert await mirror_banners.send(api, 55, mirror_banners.WELCOME, "меню", keyboard) is False
    assert api.calls == [], "зеркало должно нарисовать текстовый экран само"


@pytest.mark.asyncio
async def test_a_long_screen_stays_text_because_telegram_cuts_captions():
    api = FakePhotoApi()
    keyboard = mirror_bot.main_menu_keyboard(has_subscription=True, trial_available=False)

    assert await mirror_banners.send(api, 55, mirror_banners.CABINET, "щ" * 1025, keyboard) is False
    assert not api.uploads


@pytest.mark.asyncio
async def test_start_greets_a_newcomer_with_the_banner(session_pool):
    api = FakePhotoApi()
    bot = mirror_bot.MirrorBot(api, session_pool)

    await bot.handle_message(
        {"from": {"id": 7100, "username": "new"}, "chat": {"id": 7100}, "text": "/start"}
    )

    assert api.uploads, "первый экран должен уйти картинкой"
    payload, path = api.uploads[0]
    assert path == mirror_banners.WELCOME
    assert "Добро пожаловать" in payload["caption"]
    assert payload["reply_markup"]["inline_keyboard"], "кнопки остаются на месте"
    assert "sendMessage" not in _methods(api), "второй копии экрана текстом быть не должно"


@pytest.mark.asyncio
async def test_a_screen_that_could_not_be_drawn_as_a_picture_arrives_as_text(session_pool):
    api = FakePhotoApi(upload_fails=True)
    bot = mirror_bot.MirrorBot(api, session_pool)

    await bot.handle_message(
        {"from": {"id": 7102, "username": "new"}, "chat": {"id": 7102}, "text": "/start"}
    )

    sent = [p for m, p in api.calls if m == "sendMessage"]
    assert sent, "человек обязан увидеть меню, даже если картинка не отправилась"
    assert "Добро пожаловать" in sent[-1]["text"]


@pytest.mark.asyncio
async def test_tapping_a_button_on_a_banner_screen_replaces_it(session_pool):
    api = FakePhotoApi()
    bot = mirror_bot.MirrorBot(api, session_pool)

    await bot.handle_callback(
        {
            "id": "cb1",
            "from": {"id": 7101, "username": "new"},
            "message": {"chat": {"id": 7101}, "message_id": 9, "photo": [{"file_id": "x"}]},
            "data": "about",
        }
    )

    methods = _methods(api)
    assert "deleteMessage" in methods, "иначе картинка повиснет над чужим экраном"
    assert "sendMessage" in methods
    assert "editMessageText" not in methods, "сообщение с фото нельзя переписать текстом"
