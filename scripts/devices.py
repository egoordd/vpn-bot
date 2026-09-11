#!/usr/bin/env python3
"""Устройства подписок: посмотреть, кто сколько занял, и сбросить привязку.

Запускается на сервере шлюза, читает ту же базу, что и выдача
(`/var/lib/unlock-subgw/devices.sqlite3`, путь меняется через DEVICE_DB).

    python3 devices.py stats              сколько устройств на подписку (вся картина)
    python3 devices.py top 20             у кого больше всего — кандидаты на раздачу ссылки
    python3 devices.py list tg_740484324  устройства одной подписки
    python3 devices.py reset tg_740484324 сбросить привязку (человек сменил телефон)

Поддержке нужен именно `reset`: без него человек, поменявший телефон, ждёт,
пока освободится слот, а это две недели.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time

DB = os.environ.get("DEVICE_DB", "/var/lib/unlock-subgw/devices.sqlite3")


def _conn() -> sqlite3.Connection:
    if not os.path.exists(DB):
        sys.exit(f"базы нет: {DB} (учёт ещё не включался)")
    return sqlite3.connect(DB)


def _plural(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return "устройств"
    return {1: "устройство", 2: "устройства", 3: "устройства", 4: "устройства"}.get(
        count % 10, "устройств"
    )


def _ago(ts: float) -> str:
    hours = (time.time() - ts) / 3600
    if hours < 1:
        return "только что"
    if hours < 48:
        return f"{int(hours)} ч назад"
    return f"{int(hours / 24)} дн назад"


def stats() -> None:
    rows = _conn().execute(
        "SELECT n, COUNT(*) FROM (SELECT username, COUNT(*) n FROM devices GROUP BY username)"
        " GROUP BY n ORDER BY n"
    ).fetchall()
    if not rows:
        print("устройств пока не записано")
        return
    total = sum(count for _, count in rows)
    print(f"подписок с устройствами: {total}")
    for devices, count in rows:
        share = 100 * count / total
        print(f"  {devices} {_plural(devices)}: {count} подписок ({share:.0f}%)")


def top(limit: int = 20) -> None:
    rows = _conn().execute(
        "SELECT username, COUNT(*) n, MAX(last_seen) seen FROM devices"
        " GROUP BY username ORDER BY n DESC, seen DESC LIMIT ?",
        (limit,),
    ).fetchall()
    for username, count, seen in rows:
        print(f"{username:24} {count:3} {_plural(count):11} последнее обращение {_ago(seen)}")


def show(username: str) -> None:
    rows = _conn().execute(
        "SELECT hwid, model, os, first_seen, last_seen FROM devices WHERE username = ?"
        " ORDER BY first_seen",
        (username,),
    ).fetchall()
    if not rows:
        print("устройств не записано")
        return
    for hwid, model, os_name, first, last in rows:
        print(f"{hwid[:16]:18} {model or '—':22} {os_name or '—':10} впервые {_ago(first):14} был {_ago(last)}")


def reset(username: str, hwid: str | None = None) -> None:
    conn = _conn()
    if hwid:
        cur = conn.execute("DELETE FROM devices WHERE username = ? AND hwid = ?", (username, hwid))
    else:
        cur = conn.execute("DELETE FROM devices WHERE username = ?", (username,))
    conn.commit()
    print(f"снято привязок: {cur.rowcount}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    command, *rest = args
    if command == "stats":
        stats()
    elif command == "top":
        top(int(rest[0]) if rest else 20)
    elif command == "list" and rest:
        show(rest[0])
    elif command == "reset" and rest:
        reset(rest[0], rest[1] if len(rest) > 1 else None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
