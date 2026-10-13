"""Минимальный клиент Telegram Bot API на aiohttp.

aiogram на бот-сервере занимает ~420 МБ на процесс (pydantic-модели всех типов
Telegram), а сервер 2 ГБ с почти полной подкачкой. Боту из меню и кнопок
хватает пяти методов API, поэтому «Марат VPN» ходит в API напрямую.
"""
from __future__ import annotations

import json
import logging
import os

import aiohttp

log = logging.getLogger("marat_bot.tg")


class TelegramError(Exception):
    pass


class Tg:
    def __init__(self, token: str):
        self._base = f"https://api.telegram.org/bot{token}/"
        self._session: aiohttp.ClientSession | None = None
        self._file_ids: dict[str, str] = {}

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=70))
        return self._session

    async def call(self, method: str, **params):
        payload = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                   for k, v in params.items() if v is not None}
        session = await self._http()
        async with session.post(self._base + method, data=payload) as resp:
            data = await resp.json(content_type=None)
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description')}")
        return data.get("result")

    async def send(self, chat_id: int, text: str, markup: dict | None = None, effect: str | None = None):
        params = dict(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup,
                      link_preview_options={"is_disabled": True})
        try:
            return await self.call("sendMessage", **params, message_effect_id=effect)
        except TelegramError:
            if not effect:
                raise
            # Эффект — украшение: если Telegram его не принял, сообщение всё равно уходит.
            log.warning("message effect %s rejected, sending without it", effect)
            return await self.call("sendMessage", **params)

    async def edit(self, chat_id: int, message_id: int, text: str, markup: dict | None = None):
        try:
            return await self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text,
                                   parse_mode="HTML", reply_markup=markup, link_preview_options={"is_disabled": True})
        except TelegramError as exc:
            if "message is not modified" in str(exc):
                return None
            raise

    async def _call_file(self, method: str, field: str, path: str, **params):
        """Тот же вызов, но с загрузкой файла (multipart)."""
        form = aiohttp.FormData()
        for key, value in params.items():
            if value is not None:
                form.add_field(key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
        with open(path, "rb") as fh:
            form.add_field(field, fh.read(), filename=os.path.basename(path), content_type="image/jpeg")
        session = await self._http()
        async with session.post(self._base + method, data=form) as resp:
            data = await resp.json(content_type=None)
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description')}")
        return data.get("result")

    def _remember(self, path: str, result) -> None:
        photos = (result or {}).get("photo") if isinstance(result, dict) else None
        if photos:
            self._file_ids[path] = photos[-1]["file_id"]

    async def send_photo(self, chat_id: int, path: str, caption: str, markup: dict | None = None,
                         effect: str | None = None):
        """Баннер с подписью. Файл грузится один раз, дальше — по file_id из Telegram."""
        params = dict(chat_id=chat_id, caption=caption, parse_mode="HTML", reply_markup=markup)
        for attempt_effect in ((effect, None) if effect else (None,)):
            try:
                if path in self._file_ids:
                    result = await self.call("sendPhoto", photo=self._file_ids[path], **params,
                                             message_effect_id=attempt_effect)
                else:
                    result = await self._call_file("sendPhoto", "photo", path, **params,
                                                   message_effect_id=attempt_effect)
                self._remember(path, result)
                return result
            except TelegramError:
                if attempt_effect is None:
                    raise
                log.warning("message effect %s rejected, sending without it", attempt_effect)
        return None

    async def edit_media(self, chat_id: int, message_id: int, path: str, caption: str, markup: dict | None = None):
        """Сменить баннер и подпись у сообщения-картинки (TelegramError, если сообщение текстовое)."""
        media = {"type": "photo", "caption": caption, "parse_mode": "HTML"}
        try:
            if path in self._file_ids:
                result = await self.call("editMessageMedia", chat_id=chat_id, message_id=message_id,
                                         media={**media, "media": self._file_ids[path]}, reply_markup=markup)
            else:
                result = await self._call_file("editMessageMedia", "banner", path, chat_id=chat_id,
                                               message_id=message_id, media={**media, "media": "attach://banner"},
                                               reply_markup=markup)
        except TelegramError as exc:
            if "message is not modified" in str(exc):
                return None
            raise
        self._remember(path, result)
        return result

    async def copy(self, chat_id: int, from_chat_id: int, message_id: int, markup: dict | None = None,
                   reply_to: int | None = None) -> int:
        """Копия сообщения любого типа (текст, фото, файл) без подписи «переслано»; возвращает id копии."""
        result = await self.call("copyMessage", chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id,
                                 reply_markup=markup,
                                 reply_parameters={"message_id": reply_to, "allow_sending_without_reply": True}
                                 if reply_to else None)
        return result["message_id"]

    async def delete(self, chat_id: int, message_id: int) -> None:
        try:
            await self.call("deleteMessage", chat_id=chat_id, message_id=message_id)
        except TelegramError:
            pass

    async def answer(self, callback_id: str, text: str | None = None, alert: bool = False):
        return await self.call("answerCallbackQuery", callback_query_id=callback_id, text=text,
                               show_alert="true" if alert else None)

    async def updates(self, offset: int | None) -> list[dict]:
        return await self.call("getUpdates", offset=offset, timeout=50,
                               allowed_updates=["message", "callback_query"]) or []

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
