"""Бот с бесплатным пробным доступом для заказчика (12.10.2026: «Марат VPN», затем «Ярослав VPN»).

Без оплаты, без картинок и без упоминаний основного проекта. Пользователь
получает учётку панели `<префикс><telegram id>` (у Марата `corp_mrt_`, у Ярослава
`corp_yar_`): четыре зарубежных сервера (Польша, Финляндия-2, Нидерланды, США).
Шлюз по шаблону префикса отдаёт её под названием бота: по пункту на страну +
«Авто-обход» + «Режим РУ-сервисов», 2 устройства, свой адрес подписки.
Каждый бот — своя служба с тем же кодом и своим окружением (MARAT_*).

Здесь — чистая логика без Telegram и сети, чтобы её можно было проверить тестами.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Один код — несколько ботов для разных заказчиков (12.10.2026: «Марат VPN», «Ярослав VPN»):
# название, префикс учёток панели, адрес подписки и оформление задаются окружением службы.
NAME = os.environ.get("MARAT_NAME", "Марат VPN").strip()
PREFIX = os.environ.get("MARAT_PREFIX", "corp_mrt_").strip()
if not re.fullmatch(r"corp_[a-z0-9]{1,8}_", PREFIX):
    # Шлюз узнаёт ссылку только по имени вида corp_<…>; длинный префикс не влезет с Telegram ID.
    raise SystemExit(f"MARAT_PREFIX должен быть вида corp_xxx_ (до 8 букв/цифр), а не {PREFIX!r}")
TRIAL_DAYS = int(os.environ.get("MARAT_TRIAL_DAYS", "3"))
TRIAL_TRAFFIC_BYTES = int(os.environ.get("MARAT_TRIAL_GB", "10")) * 1024**3
DEVICES = int(os.environ.get("MARAT_DEVICES", "2"))
SUB_BASE = os.environ.get("MARAT_SUB_BASE", "https://m.212.233.122.241.sslip.io").rstrip("/")
INBOUNDS = {
    "vless": [
        "VLESS Reality PL",
        "VLESS Reality FI2",
        "VLESS Reality AMS",
        "VLESS Reality US2",
    ]
}
PROXIES = {"vless": {"flow": "xtls-rprx-vision"}}


def _plans(raw: str) -> tuple[tuple[int, str, int], ...]:
    """«дни:подпись:цена; …» → ((дни, подпись, цена), …). Оплата пока заглушка — цены только для витрины."""
    plans = []
    for item in raw.split(";"):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) == 3 and parts[0].isdigit() and parts[2].isdigit():
            plans.append((int(parts[0]), parts[1], int(parts[2])))
    return tuple(plans)


PLANS = _plans(os.environ.get(
    "MARAT_PLANS", "30:1 месяц:199; 90:3 месяца:549; 180:6 месяцев:999; 365:12 месяцев:1799"
))
MSK = timezone(timedelta(hours=3))
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря")


def panel_username(telegram_id: int) -> str:
    return f"{PREFIX}{int(telegram_id)}"


def trial_expire(now: float | None = None) -> int:
    return int((now if now is not None else time.time()) + TRIAL_DAYS * 86400)


def token_from_url(subscription_url: str | None) -> str | None:
    """Токен из ссылки панели «…/sub/<токен>»."""
    if not subscription_url or "/sub/" not in subscription_url:
        return None
    token = subscription_url.rsplit("/sub/", 1)[-1].strip("/").split("/", 1)[0]
    return token or None


def sub_link(token: str) -> str:
    return f"{SUB_BASE}/sub/{token}"


def happ_link(token: str) -> str:
    """Страница, которая открывает Happ и добавляет подписку (Telegram не пускает happ:// в кнопки)."""
    return f"{SUB_BASE}/happ/{token}"


def date_msk(ts: int) -> str:
    moment = datetime.fromtimestamp(ts, MSK)
    return f"{moment.day} {MONTHS[moment.month - 1]}, {moment:%H:%M} МСК"


def gb(value: int) -> str:
    return f"{value / 1024**3:.1f}".replace(".", ",")


def days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} дня"
    return f"{n} дней"


def time_left(expire: int, now: float | None = None) -> str:
    """Сколько осталось: «2 дня 14 ч», «5 ч 20 мин», «меньше минуты»."""
    seconds = int(expire - (now if now is not None else time.time()))
    if seconds <= 0:
        return "0 мин"
    days, rest = divmod(seconds, 86400)
    hours, minutes = rest // 3600, rest % 3600 // 60
    if days:
        return f"{days_word(days)} {hours} ч" if hours else days_word(days)
    if hours:
        return f"{hours} ч {minutes} мин" if minutes else f"{hours} ч"
    return f"{minutes} мин" if minutes else "меньше минуты"


def bar(part: float, total: float, width: int = 10, full: str = "▰", empty: str = "▱") -> str:
    """Полоска заполнения ▰▰▰▱▱▱ — для трафика."""
    filled = 0 if total <= 0 else min(width, max(0, round(width * part / total)))
    return full * filled + empty * (width - filled)


def per_month(days: int, price: int) -> int:
    return round(price * 30 / days)


@dataclass(frozen=True)
class Access:
    username: str
    token: str | None
    expire: int | None
    status: str
    used_bytes: int
    limit_bytes: int

    @property
    def active(self) -> bool:
        return self.status == "active" and (self.expire is None or self.expire > time.time())


class Store:
    """Кто брал пробный доступ (+ имя в Telegram для админки) и кто админ.

    Источник правды о сроке — панель, здесь только факт выдачи. Админ, заданный
    ником, привязывается к Telegram ID при первом сообщении: если ник потом
    перейдёт к другому человеку, тот админом не станет."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT NOT NULL, created_at INTEGER NOT NULL)"
        )
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(users)")}
        for column in ("tg_username", "first_name"):
            if column not in columns:
                self._db.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
        self._db.execute("CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, telegram_id INTEGER NOT NULL)")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS support_links (admin_chat INTEGER NOT NULL, admin_msg INTEGER NOT NULL, "
            "user_id INTEGER NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY (admin_chat, admin_msg))"
        )
        self._db.commit()

    def get(self, telegram_id: int) -> str | None:
        row = self._db.execute("SELECT username FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return row[0] if row else None

    def add(self, telegram_id: int, username: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, created_at) VALUES (?, ?, ?)",
            (telegram_id, username, int(time.time())),
        )
        self._db.commit()

    def touch(self, telegram_id: int, tg_username: str | None, first_name: str | None) -> None:
        """Обновить ник и имя у того, кто уже брал доступ (для списка в админке)."""
        self._db.execute(
            "UPDATE users SET tg_username = ?, first_name = ? WHERE telegram_id = ?",
            (tg_username, first_name, telegram_id),
        )
        self._db.commit()

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def created_since(self, since: float) -> int:
        return self._db.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (int(since),)).fetchone()[0]

    def row(self, telegram_id: int) -> UserRow | None:
        found = self._db.execute(
            "SELECT telegram_id, username, created_at, tg_username, first_name FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return UserRow(*found) if found else None

    def recent(self, limit: int) -> list[UserRow]:
        rows = self._db.execute(
            "SELECT telegram_id, username, created_at, tg_username, first_name FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [UserRow(*r) for r in rows]

    def admin_id(self, username: str) -> int | None:
        row = self._db.execute("SELECT telegram_id FROM admins WHERE username = ?", (username,)).fetchone()
        return row[0] if row else None

    def bind_admin(self, username: str, telegram_id: int) -> None:
        self._db.execute("INSERT OR IGNORE INTO admins (username, telegram_id) VALUES (?, ?)", (username, telegram_id))
        self._db.commit()

    def link_support(self, admin_chat: int, admin_msg: int, user_id: int) -> None:
        """Сообщение обращения в чате админа → кто писал (чтобы ответ «реплаем» дошёл до него)."""
        self._db.execute(
            "INSERT OR REPLACE INTO support_links (admin_chat, admin_msg, user_id, created_at) VALUES (?, ?, ?, ?)",
            (admin_chat, admin_msg, user_id, int(time.time())),
        )
        self._db.commit()

    def support_user(self, admin_chat: int, admin_msg: int) -> int | None:
        row = self._db.execute(
            "SELECT user_id FROM support_links WHERE admin_chat = ? AND admin_msg = ?", (admin_chat, admin_msg)
        ).fetchone()
        return row[0] if row else None


@dataclass(frozen=True)
class UserRow:
    telegram_id: int
    username: str
    created_at: int
    tg_username: str | None
    first_name: str | None
