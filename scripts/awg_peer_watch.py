"""Сторож AmneziaWG-клиентов на роутерах (11.10.2026, клиент с Keenetic в Якутске).

Раз в 5 минут (unlock-awg-watch.timer) спрашивает у польского сервера время последних
рукопожатий входа awg1 и пишет в бот уведомлений, только когда роутер клиента пропал
дольше чем на STALE_SECONDS или снова появился. Роутер шлёт keepalive каждые 25 с,
так что рукопожатие у живого подключения обновляется примерно раз в 2 минуты.

Польский сервер пускает ключ сторожа только на одну команду (forced command
`awg show awg1 latest-handshakes`), поэтому сторож ничего не может там изменить.

Настройки (окружение):
  AWG_WATCH       «публичный ключ|подпись; ключ2|подпись2» — кого сторожить
  AWG_WATCH_HOST  адрес польского сервера (по умолчанию 78.17.154.225)
  AWG_WATCH_KEY   ключ SSH (по умолчанию /root/.ssh/awg_watch)
  AWG_WATCH_STATE файл состояния (по умолчанию /var/lib/unlock-awg-watch/state.json)
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

STALE_SECONDS = 15 * 60
FETCH_FAILS_BEFORE_ALERT = 3
MSK = timezone(timedelta(hours=3))


def parse_handshakes(text: str) -> dict[str, int]:
    """Вывод `awg show <if> latest-handshakes`: «ключ<TAB>unix-время» по строке."""
    result: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            result[parts[0]] = int(parts[1])
    return result


def parse_watch(raw: str) -> dict[str, str]:
    """«ключ|подпись; ключ2|подпись2» → {ключ: подпись}. Ключи base64 сами содержат «=»."""
    watch: dict[str, str] = {}
    for item in raw.split(";"):
        key, sep, label = item.strip().partition("|")
        if key and sep:
            watch[key.strip()] = label.strip() or key.strip()
    return watch


def _msk(ts: int) -> str:
    return datetime.fromtimestamp(ts, MSK).strftime("%d.%m %H:%M") if ts else "никогда"


def evaluate(
    prev: dict[str, str], handshakes: dict[str, int], now: int, watch: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Новое состояние каждого роутера и сообщения о сменах. Первый запуск — молча."""
    state: dict[str, str] = {}
    messages: list[str] = []
    for key, label in watch.items():
        ts = handshakes.get(key, 0)
        status = "up" if ts and now - ts <= STALE_SECONDS else "down"
        state[key] = status
        before = prev.get(key)
        if before == "up" and status == "down":
            messages.append(
                f"🔴 <b>{label}</b>: роутер не на связи больше {STALE_SECONDS // 60} мин. "
                f"Последнее рукопожатие: {_msk(ts)} МСК. Возможно, роутер выключен или пропал интернет у клиента."
            )
        elif before == "down" and status == "up":
            messages.append(f"🟢 <b>{label}</b>: роутер снова на связи (рукопожатие {_msk(ts)} МСК).")
    return state, messages


def fetch(host: str, key_path: str) -> str:
    cmd = [
        "ssh", "-i", key_path, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=accept-new", f"root@{host}", "latest-handshakes",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=40, check=True).stdout


def _load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


async def _send(messages: list[str]) -> None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from services.alerts import send_alert

    for text in messages:
        if not await send_alert(text):
            print("не удалось отправить уведомление:", text, file=sys.stderr)


def main() -> int:
    watch = parse_watch(os.environ.get("AWG_WATCH", ""))
    if not watch:
        print("AWG_WATCH пуст — сторожить некого", file=sys.stderr)
        return 1
    host = os.environ.get("AWG_WATCH_HOST", "78.17.154.225")
    key_path = os.environ.get("AWG_WATCH_KEY", "/root/.ssh/awg_watch")
    state_path = os.environ.get("AWG_WATCH_STATE", "/var/lib/unlock-awg-watch/state.json")
    saved = _load(state_path)

    try:
        handshakes = parse_handshakes(fetch(host, key_path))
    except (subprocess.SubprocessError, OSError) as exc:
        fails = int(saved.get("fetch_fails", 0)) + 1
        saved["fetch_fails"] = fails
        _save(state_path, saved)
        print(f"польский сервер не ответил ({fails} раз подряд): {exc}", file=sys.stderr)
        if fails == FETCH_FAILS_BEFORE_ALERT:
            asyncio.run(_send([f"⚠️ Сторож роутеров не может связаться с польским сервером {host} уже {fails} раза подряд."]))
        return 1

    messages: list[str] = []
    if int(saved.get("fetch_fails", 0)) >= FETCH_FAILS_BEFORE_ALERT:
        messages.append(f"✅ Сторож роутеров снова видит польский сервер {host}.")
    peers, changes = evaluate(saved.get("peers", {}), handshakes, int(time.time()), watch)
    messages += changes
    _save(state_path, {"peers": peers, "fetch_fails": 0, "checked_at": int(time.time())})
    if messages:
        asyncio.run(_send(messages))
    print(json.dumps(peers, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
