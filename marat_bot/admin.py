"""Админка «Марат VPN» (12.10.2026): статистика, пользователи, продление, трафик.

Админы — MARAT_ADMINS: Telegram ID и/или ники через запятую («maratkam1, 123»).
Ник привязывается к ID при первом сообщении (см. Store). Менять можно только
учётки этого бота (corp_mrt_<id>) — к остальным пользователям панели админка
доступа не даёт.
"""
from __future__ import annotations

import html
import logging
import os
import time
from datetime import datetime, timezone

from marat_bot.core import PREFIX, Access, Store, UserRow, bar, date_msk, gb, panel_username, time_left

log = logging.getLogger("marat_bot.admin")

MAX_EXTEND_DAYS = 365
MAX_TRAFFIC_GB = 2000
RECENT_LIMIT = 15
COMMANDS = ("/admin", "/users", "/user", "/extend", "/traffic")
MENU_COMMANDS = [
    {"command": "admin", "description": "🛠 Админка: статистика"},
    {"command": "users", "description": "👥 Последние пользователи"},
    {"command": "user", "description": "👤 Карточка: /user ID"},
    {"command": "extend", "description": "⏩ Продлить: /extend ID ДНИ"},
    {"command": "traffic", "description": "📶 Трафик: /traffic ID ГБ"},
]


def parse_admins(raw: str) -> tuple[frozenset[int], frozenset[str]]:
    ids: set[int] = set()
    names: set[str] = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip().lstrip("@").lower()
        if item.isdigit():
            ids.add(int(item))
        elif item:
            names.add(item)
    return frozenset(ids), frozenset(names)


ADMIN_IDS, ADMIN_NAMES = parse_admins(os.environ.get("MARAT_ADMINS", ""))


def is_admin(store: Store, user: dict) -> bool:
    uid = user.get("id")
    if not isinstance(uid, int):
        return False
    if uid in ADMIN_IDS:
        return True
    name = (user.get("username") or "").lower()
    if not name or name not in ADMIN_NAMES:
        return False
    bound = store.admin_id(name)
    if bound is None:
        store.bind_admin(name, uid)
        log.warning("admin @%s bound to telegram id %s", name, uid)
        return True
    if bound != uid:
        log.warning("admin @%s is bound to %s, rejected %s", name, bound, uid)
    return bound == uid


def _quote(*lines: str) -> str:
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


def _who(row: UserRow | None) -> str:
    if row is None:
        return "—"
    parts = [html.escape(row.first_name)] if row.first_name else []
    if row.tg_username:
        parts.append(f"@{html.escape(row.tg_username)}")
    return " ".join(parts) or "без имени"


def _online_since(value: str | None) -> float | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()


def _access(record: dict) -> Access:
    return Access(
        username=record.get("username", ""), token=None, expire=record.get("expire") or None,
        status=record.get("status", ""), used_bytes=record.get("used_traffic") or 0,
        limit_bytes=record.get("data_limit") or 0,
    )


def _state(access: Access) -> str:
    if access.active:
        return f"🟢 {time_left(access.expire)}" if access.expire else "🟢 без срока"
    if access.status == "limited":
        return "🟠 трафик кончился"
    return "🔴 закончился"


async def _bot_users(client) -> dict[str, dict]:
    return {u["username"]: u for u in await client.list_users(limit=5000) if u.get("username", "").startswith(PREFIX)}


async def panel_text(store: Store, client) -> str:
    users = await _bot_users(client)
    now = time.time()
    active = sum(1 for u in users.values() if _access(u).active)
    online = sum(1 for u in users.values() if (_online_since(u.get("online_at")) or 0) > now - 86400)
    traffic = sum(u.get("used_traffic") or 0 for u in users.values())
    return (
        "🛠 <b>Админка · Марат VPN</b>\n\n"
        + _quote(
            f"👥 Пользователей: <b>{store.count()}</b>",
            f"🟢 Доступ активен: <b>{active}</b>",
            f"📡 Были онлайн за сутки: <b>{online}</b>",
            f"🆕 Новых: сегодня {store.created_since(now - 86400)} · за 7 дней {store.created_since(now - 7 * 86400)}",
            f"📶 Трафик всего: {gb(traffic)} ГБ",
        )
        + "\n\n<b>Команды</b>\n"
        + _quote(
            "/users — последние пользователи",
            "/user ID — карточка пользователя",
            f"/extend ID ДНИ — продлить доступ (1–{MAX_EXTEND_DAYS} дней)",
            "/traffic ID ГБ — лимит трафика (0 — без лимита), счётчик обнуляется",
            "/admin — эта панель",
        )
        + "\nID пользователя — в списке /users или в его разделе «Помощь»."
    )


async def users_text(store: Store, client) -> str:
    rows = store.recent(RECENT_LIMIT)
    if not rows:
        return "👥 <b>Пользователи</b>\n\nПока никто не брал пробный доступ."
    users = await _bot_users(client)
    lines = []
    for row in rows:
        record = users.get(row.username)
        state = _state(_access(record)) if record else "⚪️ нет в панели"
        used = f" · {gb(record.get('used_traffic') or 0)} ГБ" if record else ""
        lines.append(f"{state} · <code>{row.telegram_id}</code> · {_who(row)}{used}")
    return (
        f"👥 <b>Последние пользователи</b> ({len(rows)} из {store.count()})\n\n"
        + _quote(*lines)
        + "\n\nПодробнее: /user ID"
    )


def _usage(text: str) -> str:
    return f"Формат: <code>{text}</code>"


def _parse_id(value: str) -> int | None:
    return int(value) if value.isdigit() and 0 < int(value) < 10**15 else None


async def user_text(store: Store, client, not_found, telegram_id: int) -> str:
    try:
        user = await client.get_user(panel_username(telegram_id))
    except not_found:
        return f"Пользователя <code>{telegram_id}</code> нет в боте."
    access = Access(user.username, None, user.expire, user.status, user.used_traffic_bytes, user.data_limit_bytes)
    row = store.row(telegram_id)
    lines = [_state(access)]
    if access.expire:
        lines.append(f"🗓 {'До' if access.active else 'Был до'} {date_msk(access.expire)}")
    if access.limit_bytes:
        lines.append(f"📶 {bar(access.used_bytes, access.limit_bytes)} {gb(access.used_bytes)} из {gb(access.limit_bytes)} ГБ")
    else:
        lines.append(f"📶 {gb(access.used_bytes)} ГБ · без лимита")
    if row:
        lines.append(f"📅 Пришёл: {date_msk(row.created_at)}")
    online = _online_since(user.online_at)
    lines.append(f"📡 Онлайн: {date_msk(int(online)) if online else 'ещё не подключался'}")
    return (
        f"👤 <b>Пользователь</b> <code>{telegram_id}</code> · {_who(row)}\n\n"
        + _quote(*lines)
        + f"\n\n/extend {telegram_id} 30 — продлить на 30 дней\n/traffic {telegram_id} 50 — лимит 50 ГБ"
    )


async def extend(client, not_found, telegram_id: int, days: int) -> tuple[str, str | None]:
    """(ответ админу, уведомление пользователю или None)."""
    username = panel_username(telegram_id)
    try:
        user = await client.get_user(username)
    except not_found:
        return f"Пользователя <code>{telegram_id}</code> нет в боте.", None
    base = max(time.time(), user.expire or 0)
    new_expire = int(base + days * 86400)
    # Срок в будущем панель сама возвращает «закончившемуся» в активные.
    updated = await client.modify_user(username, expire_at=new_expire)
    log.warning("admin extend %s by %s days -> %s", username, days, new_expire)
    reply = f"✅ <code>{telegram_id}</code>: доступ продлён на {days} дн. — до <b>{date_msk(new_expire)}</b>."
    if updated.status == "limited":
        reply += f"\n⚠️ Трафик исчерпан — обнулить: /traffic {telegram_id} ГБ"
    return reply, f"🎁 <b>Доступ продлён</b> до <b>{date_msk(new_expire)}</b>. Хорошего пользования!"


async def set_traffic(client, not_found, telegram_id: int, limit_gb: int) -> tuple[str, str | None]:
    username = panel_username(telegram_id)
    try:
        await client.get_user(username)
    except not_found:
        return f"Пользователя <code>{telegram_id}</code> нет в боте.", None
    await client.modify_user(username, data_limit_bytes=limit_gb * 1024**3)
    await client.reset_user_data_usage(username)
    log.warning("admin traffic %s -> %s GB, counter reset", username, limit_gb)
    label = f"{limit_gb} ГБ" if limit_gb else "без лимита"
    return (
        f"✅ <code>{telegram_id}</code>: трафик {label}, счётчик обнулён.",
        f"📶 <b>Трафик обновлён</b>: {label}.",
    )


async def handle(tg, chat: int, command: str, args: list[str], store: Store, client, not_found) -> None:
    """Команды админки. Проверка прав — у вызывающего."""
    if command == "/admin":
        await tg.send(chat, await panel_text(store, client), keyboard())
        return
    if command == "/users":
        await tg.send(chat, await users_text(store, client), keyboard())
        return
    if command == "/user":
        telegram_id = _parse_id(args[0]) if args else None
        text = await user_text(store, client, not_found, telegram_id) if telegram_id else _usage("/user ID")
        await tg.send(chat, text)
        return
    usage = "/extend ID ДНИ" if command == "/extend" else "/traffic ID ГБ"
    telegram_id = _parse_id(args[0]) if len(args) == 2 else None
    amount = int(args[1]) if len(args) == 2 and args[1].isdigit() else None
    if command == "/extend":
        if not telegram_id or amount is None or not 1 <= amount <= MAX_EXTEND_DAYS:
            await tg.send(chat, _usage(usage) + f" — дней от 1 до {MAX_EXTEND_DAYS}")
            return
        reply, notice = await extend(client, not_found, telegram_id, amount)
    else:
        if not telegram_id or amount is None or amount > MAX_TRAFFIC_GB:
            await tg.send(chat, _usage(usage) + f" — от 0 (без лимита) до {MAX_TRAFFIC_GB}")
            return
        reply, notice = await set_traffic(client, not_found, telegram_id, amount)
    if notice:
        try:
            await tg.send(telegram_id, notice)
        except Exception:
            log.warning("could not notify %s", telegram_id)
            reply += "\n(уведомить пользователя не удалось — возможно, он остановил бота)"
    await tg.send(chat, reply)


def keyboard() -> dict:
    return {"inline_keyboard": [
        [{"text": "🔄 Обновить", "callback_data": "adm"}, {"text": "👥 Пользователи", "callback_data": "adm:users"}],
        [{"text": "◀️ В меню", "callback_data": "menu"}],
    ]}


async def set_menu(tg, chat: int, base_commands: list[dict]) -> None:
    """Команды админки в меню Telegram — только в чате админа."""
    try:
        await tg.call("setMyCommands", commands=base_commands + MENU_COMMANDS, scope={"type": "chat", "chat_id": chat})
    except Exception:
        log.exception("admin menu for %s failed", chat)
