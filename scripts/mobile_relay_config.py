#!/usr/bin/env python3
"""Xray-конфиг для входа в российском облаке («📶 Мобильный интернет»).

Когда оператор опускает мобильный интернет до белого списка, туннель выживает
при двух условиях сразу: первый узел стоит на российском адресе, и рукопожатие
называет разрешённую службу. Этот вход даёт и то, и другое — он живёт в
российском облаке, а в SNI у него `max.ru`, и Reality направляет неопознанные
соединения на настоящий max.ru, так что проверяющий видит его сертификат.

Конфиг собирается из уже работающего московского моста: оттуда берутся выходы на
наши зарубежные узлы вместе с их учётными данными и DNS. Меняется только вход и
маршрутизация — здесь она через балансировщик, чтобы упавший выход не забирал с
собой весь режим (у московского моста каждый порт жёстко привязан к одной стране,
и это как раз то, что мы чиним).

    ssh runode 'cat /usr/local/etc/xray/config.json' |
        python3 scripts/mobile_relay_config.py --uuid … --private-key … --short-id … > mobile.json
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

DEFAULT_SNI = "max.ru"
DEFAULT_PORT = 443
DEFAULT_EXITS = ("pl", "de")
PROBE_URL = "http://www.gstatic.com/generate_204"
# Тот же интервал, что в клиентском «Авто-обходе»: упавший выход заменяется за
# минуту, а не за три, и при этом проба не дёргает туннели каждые пятнадцать секунд.
PROBE_INTERVAL = "60s"
# Мобильный оператор рвёт простаивающее соединение примерно через двадцать минут
# (NAT-таблица провайдера), поэтому keepalive обязателен на обеих сторонах.
KEEPALIVE = {"tcpKeepAliveIdle": 30, "tcpKeepAliveInterval": 25}


class TemplateError(ValueError):
    """В образце нет того, без чего вход не собрать."""


def _outbound(template: dict[str, Any], tag: str) -> dict[str, Any]:
    for outbound in template.get("outbounds", []):
        if outbound.get("tag") == tag:
            return outbound
    raise TemplateError(f"в образце нет выхода {tag!r}")


def build_config(
    template: dict[str, Any],
    *,
    uuid: str,
    private_key: str,
    short_id: str,
    exits: tuple[str, ...] = DEFAULT_EXITS,
    sni: str = DEFAULT_SNI,
    port: int = DEFAULT_PORT,
) -> dict[str, Any]:
    """Конфиг входа: Reality под именем `sni` → балансировщик по `exits`."""

    if not (uuid and private_key and short_id):
        raise ValueError("нужны uuid, приватный ключ и short id")
    if not exits:
        raise ValueError("нужен хотя бы один выход")

    inbound = {
        "tag": "in-mobile",
        "listen": "0.0.0.0",
        "port": port,
        "protocol": "vless",
        "settings": {
            "clients": [{"id": uuid, "flow": "xtls-rprx-vision"}],
            "decryption": "none",
        },
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "show": False,
                # Неопознанные соединения уходят на настоящую службу, поэтому
                # сканер получает её собственный сертификат, а не наш.
                "dest": f"{sni}:443",
                "xver": 0,
                "serverNames": [sni],
                "privateKey": private_key,
                "shortIds": [short_id],
            },
            "sockopt": dict(KEEPALIVE),
        },
        "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
    }

    outbounds = [_outbound(template, "direct"), _outbound(template, "block")]
    outbounds += [_outbound(template, tag) for tag in exits]

    routing = {
        "domainStrategy": template.get("routing", {}).get("domainStrategy", "AsIs"),
        "rules": [
            # Торренты не выпускаем: жалобы правообладателей приходят хостеру,
            # а российский хостер снимает сервер быстрее любого зарубежного.
            {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"},
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
            # Российские адреса уходят с российского же адреса входа: банки и
            # госуслуги продолжают работать, а на зарубежный узел идёт только то,
            # ради чего человек включил VPN.
            {"type": "field", "ip": ["geoip:ru"], "outboundTag": "direct"},
            {
                "type": "field",
                "domain": ["geosite:category-ru", "geosite:category-gov-ru"],
                "outboundTag": "direct",
            },
            {"type": "field", "network": "tcp,udp", "balancerTag": "exits"},
        ],
        "balancers": [
            {"tag": "exits", "selector": list(exits), "strategy": {"type": "leastPing"}}
        ],
    }

    return {
        "log": {"loglevel": "warning"},
        "dns": template.get("dns", {"servers": ["77.88.8.8", "8.8.8.8"]}),
        "inbounds": [inbound],
        "outbounds": outbounds,
        "routing": routing,
        "observatory": {
            "subjectSelector": list(exits),
            "probeUrl": PROBE_URL,
            "probeInterval": PROBE_INTERVAL,
            # Пробы по очереди, а не залпом: залп из нескольких туннелей раз в
            # минуту выглядит для оператора как всплеск подключений.
            "enableConcurrency": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uuid", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--short-id", required=True)
    parser.add_argument("--sni", default=DEFAULT_SNI)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--exits", default=",".join(DEFAULT_EXITS))
    args = parser.parse_args()

    template = json.load(sys.stdin)
    config = build_config(
        template,
        uuid=args.uuid,
        private_key=args.private_key,
        short_id=args.short_id,
        exits=tuple(tag.strip() for tag in args.exits.split(",") if tag.strip()),
        sni=args.sni,
        port=args.port,
    )
    json.dump(config, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
