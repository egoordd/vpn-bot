#!/usr/bin/env python3
"""Сколько устройств пользуется одной ссылкой-подпиской.

Считает не по адресам подключений, а по строке клиента, которую приложение
присылает при обновлении подписки. Так задача решается без журналов на нодах,
без доступа к Германии и Нидерландам, где у нас нет шелла, и без единого байта
о том, что человек открывает.

Две ловушки, каждая из которых сама по себе даёт неверный ответ:

1. Happ подмешивает в идентификатор текущую дату. Одно устройство сообщает два
   значения, отличающиеся третьей цифрой с конца, чередуясь по чётности дня.
   Без нормализации счёт завышается примерно в полтора раза: 160 «устройств»
   против 106 настоящих на выборке за неделю.

2. Мессенджеры открывают ссылку сами, чтобы показать предпросмотр. TelegramBot,
   GoogleMessages и WhatsApp в журнале — это не устройства клиента. Зато их
   появление означает, что ссылку куда-то вставили, и это отдельный сигнал.

Запуск на бот-сервере:
    journalctl -u unlock-subgw --since "7 days ago" --no-pager | python3 device_report.py
"""
import base64
import collections
import re
import sys

LINE = re.compile(r"served token=(\S+?)…?\s+flavor=\S+\s+entries=\d+\s+client='([^']*)'")
HAPP = re.compile(r"Happ/[\d.]+/([A-Za-z]+)/(\d{6,})")
CRAWLERS = ("TelegramBot", "GoogleMessages", "WhatsApp", "Twitterbot", "facebookexternalhit")


def device_key(client: str) -> tuple[str, bool]:
    """(идентификатор устройства, это ли предпросмотрщик)."""
    if any(client.startswith(c) for c in CRAWLERS):
        return client.split("/")[0], True
    m = HAPP.match(client)
    if m:
        platform, ident = m.group(1), m.group(2)
        return f"Happ/{platform}/{ident[:-3]}", False       # см. ловушку 1
    app = re.match(r"([A-Za-z0-9]+)", client)
    return f"{app.group(1) if app else client[:16]}/без-id", False


def decode(token: str) -> str:
    try:
        return base64.b64decode(token + "=" * (-len(token) % 4)).decode("utf-8", "replace")
    except Exception:
        return token


def main() -> int:
    devices: dict[str, set[str]] = collections.defaultdict(set)
    shared: dict[str, set[str]] = collections.defaultdict(set)
    for line in sys.stdin:
        m = LINE.search(line)
        if not m:
            continue
        token, client = m.groups()
        key, is_crawler = device_key(client)
        (shared if is_crawler else devices)[token].add(key)

    if not devices:
        print("В журнале нет обращений за подпиской.")
        return 0

    print(f"аккаунтов в выборке: {len(devices)}")
    print(f"устройств всего    : {sum(len(v) for v in devices.values())}\n")

    dist = collections.Counter(len(v) for v in devices.values())
    print("устройств на аккаунт:")
    for n in sorted(dist):
        print(f"   {n:>2}: {dist[n]:>3} аккаунтов  {'#' * dist[n]}")

    heavy = sorted(((t, d) for t, d in devices.items() if len(d) > 5), key=lambda kv: -len(kv[1]))
    print(f"\nбольше пяти устройств: {len(heavy)}")
    for token, devs in heavy:
        print(f"   {decode(token):<14} {len(devs)}")
        for d in sorted(devs):
            print(f"        {d}")

    if shared:
        print(f"\nссылку открывал предпросмотрщик мессенджера: {len(shared)} аккаунт(ов)")
        print("   (значит ссылку куда-то вставили — сама по себе не улика, но повод посмотреть)")
        for token, bots in sorted(shared.items()):
            print(f"   {decode(token):<14} {', '.join(sorted(bots))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
