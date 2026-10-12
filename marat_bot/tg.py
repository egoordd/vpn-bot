"""Минимальный клиент Telegram Bot API на aiohttp.

aiogram на бот-сервере занимает ~420 МБ на процесс (pydantic-модели всех типов
Telegram), а сервер 2 ГБ с почти полной подкачкой. Боту из меню и кнопок
хватает пяти методов API, поэтому «Марат VPN» ходит в API напрямую.
"""
from __future__ import annotations

import json
import logging

import aiohttp

log = logging.getLogger("marat_bot.tg")


class TelegramError(Exception):
    pass


class Tg:
    def __init__(self, token: str):
        self._base = f"https://api.telegram.org/bot{token}/"
        self._session: aiohttp.ClientSession | None = None

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

    async def send(self, chat_id: int, text: str, markup: dict | None = None):
        return await self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                               reply_markup=markup, link_preview_options={"is_disabled": True})

    async def edit(self, chat_id: int, message_id: int, text: str, markup: dict | None = None):
        try:
            return await self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text,
                                   parse_mode="HTML", reply_markup=markup, link_preview_options={"is_disabled": True})
        except TelegramError as exc:
            if "message is not modified" in str(exc):
                return None
            raise

    async def answer(self, callback_id: str, text: str | None = None, alert: bool = False):
        return await self.call("answerCallbackQuery", callback_query_id=callback_id, text=text,
                               show_alert="true" if alert else None)

    async def updates(self, offset: int | None) -> list[dict]:
        return await self.call("getUpdates", offset=offset, timeout=50,
                               allowed_updates=["message", "callback_query"]) or []

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
