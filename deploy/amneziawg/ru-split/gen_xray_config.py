"""Конфиг xray для РУ-режима роутеров на польском узле (AmneziaWG awg1).

Роутер шлёт в туннель всё подряд, делить трафик по сайтам он не умеет — делит
узел. TCP клиентов awg1 заворачивается (REDIRECT) в этот xray; он узнаёт имя
сайта из TLS/HTTP и по тем же спискам, что РУ-режим на телефоне
(services/xray_json.py), отправляет российское через релей на VK Cloud
(ключ relay-ru с правилом «всё напрямую» — выход с российского адреса VK),
остальное — напрямую с польского адреса. Если VK не отвечает (его гасят за
баланс), российское временно выходит с польского адреса, а не ломается.

Запуск из корня репозитория:
  python3 deploy/amneziawg/ru-split/gen_xray_config.py <uuid ключа relay-ru на VK> > config.json
"""
import json
import sys

sys.path.insert(0, ".")
from services import xray_json as x  # noqa: E402

LISTEN_PORT = 12345
RELAY_HOST = "212.233.122.241"
RELAY_SNI = "212.233.122.241.sslip.io"
RELAY_PORT = 443
RELAY_PBK = "wFKeoKPvWFvkKLnJ2E7qcNfF2UbZdOru_MjZjRUffFA"
RELAY_SID = "616e3630f94bab80"
RU = "ru"
PROBE = "https://www.gstatic.com/generate_204"


def build(relay_uuid: str) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "awg-ru",
                "listen": "0.0.0.0",
                "port": LISTEN_PORT,
                "protocol": "dokodemo-door",
                "settings": {"network": "tcp", "followRedirect": True},
                # routeOnly: имя нужно только для выбора выхода, соединение
                # идёт на тот адрес, который клиент и так выбрал.
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": True},
            }
        ],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {
                "tag": x.RU_VIA_TAG,
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": RELAY_HOST,
                            "port": RELAY_PORT,
                            "users": [{"id": relay_uuid, "encryption": "none", "flow": "xtls-rprx-vision"}],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": RELAY_SNI,
                        "fingerprint": "firefox",
                        "publicKey": RELAY_PBK,
                        "shortId": RELAY_SID,
                    },
                },
            },
        ],
        "observatory": {"subjectSelector": [x.RU_VIA_TAG], "probeURL": PROBE, "probeInterval": "1m"},
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "balancers": [
                {"tag": RU, "selector": [x.RU_VIA_TAG], "strategy": {"type": "leastPing"}, "fallbackTag": "direct"}
            ],
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                {"type": "field", "domain": x._RU_DIRECT_DOMAINS + x._RU_APPS_DIRECT, "balancerTag": RU},
                {"type": "field", "domain": x._FORCE_PROXY_DOMAINS, "outboundTag": "direct"},
                {"type": "field", "ip": ["geoip:ru"], "balancerTag": RU},
                {"type": "field", "network": "tcp,udp", "outboundTag": "direct"},
            ],
        },
    }


if __name__ == "__main__":
    json.dump(build(sys.argv[1]), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
