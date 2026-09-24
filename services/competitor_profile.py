"""Тестовая копия автовыбора конкурента на наших серверах.

Отдаётся только по ссылке ``/sub/<токен>/test``: владелец ставит её рядом со
своей обычной подпиской и сравнивает с «⚡️ Авто-обходом». Клиентам не
выдаётся — 24.09.2026 эти же настройки на пару минут попали в общую подписку,
и владелец их откатил: сначала тест.

Снято с работающего конфига «🇪🇺 ⚡️ Автовыбор ⚡️» Phantom VPN (Happ,
24.09.2026) и повторено один в один: стратегия, проверка серверов, правила
маршрутизации, DNS, параметры QUIC у Hysteria2. Отличаются только серверы —
здесь наши, по одному на каждый адрес, плюс первый Hysteria2, как у них.
Чего повторить нельзя без работ на серверах: у них Reality слушает порт 443
и представляется поддоменом собственного домена.
"""

from __future__ import annotations

try:
    from services.xray_json import _INBOUNDS, _parse_uri, build_outbound
except ImportError:  # pragma: no cover - standalone deploy path, как у шлюза
    from xray_json import _INBOUNDS, _parse_uri, build_outbound

TEST_REMARKS = "🧪 Тест · автовыбор как у Phantom"

_BALANCER_TAG = "Balancer_R"
_OUTBOUND_PREFIX = "r"
_PROBE_URL = "http://www.gstatic.com/generate_204"

_STRATEGY = {
    "type": "leastLoad",
    "settings": {"baselines": ["1s"], "expected": 2, "maxRTT": "3s", "tolerance": 0.5},
}
_BURST_OBSERVATORY = {
    "subjectSelector": [_OUTBOUND_PREFIX],
    "pingConfig": {
        "connectivity": "",
        "destination": _PROBE_URL,
        "interval": "2m",
        "sampling": 3,
        "timeout": "1s",
    },
}
_DNS = {
    "queryStrategy": "UseIP",
    "servers": [
        {"address": "https://1.1.1.1/dns-query", "skipFallback": False},
        {"address": "https://8.8.8.8/dns-query", "skipFallback": False},
    ],
    "tag": "dns_out",
}
_QUIC_PARAMS = {"congestion": "bbr", "debug": False, "keepAlivePeriod": 10, "maxIdleTimeout": 120}

_IP_CHECK_DOMAINS = ["domain:2ip.ru", "domain:2ip.io"]

# Их список «напрямую», слово в слово.
_DIRECT_DOMAINS = [
    "geosite:private",
    "domain:mtalk.google.com",
    "domain:push.apple.com",
    "domain:api.push.apple.com",
    "domain:push-apple.com.akadns.net",
    "domain:courier.push.apple.com",
    "domain:mangabuff.ru",
    "domain:vk.com",
    "domain:vk.ru",
    "domain:vk.me",
    "domain:vkontakte.ru",
    "domain:vkvideo.ru",
    "domain:vkuservideo.net",
    "domain:vkuser.net",
    "domain:vkcdn.net",
    "regexp:^.*\\.vk\\.com$",
    "regexp:^.*\\.userapi\\.com$",
    "domain:ok.ru",
    "domain:odnoklassniki.ru",
    "domain:mycdn.me",
    "domain:rutube.ru",
    "domain:rutubeimg.com",
    "domain:dzen.ru",
    "domain:zen.yandex.ru",
    "domain:kinopoisk.ru",
    "domain:ivi.ru",
    "domain:okko.tv",
    "domain:premier.one",
    "domain:more.tv",
    "domain:start.ru",
    "domain:wink.ru",
    "domain:kion.ru",
    "domain:yandex.ru",
    "domain:yandex.com",
    "domain:yandex.net",
    "domain:ya.ru",
    "domain:yastatic.net",
    "domain:yandex-team.ru",
    "domain:eda.yandex.ru",
    "domain:lavka.yandex.ru",
    "domain:market.yandex.ru",
    "domain:music.yandex.ru",
    "domain:disk.yandex.ru",
    "domain:taxi.yandex.ru",
    "domain:mail.ru",
    "domain:mail.com",
    "domain:max.ru",
    "domain:web.max.ru",
    "domain:lk.max.ru",
    "domain:api.max.ru",
    "domain:imgsmail.ru",
    "domain:ozon.ru",
    "domain:cdn.ozon.ru",
    "domain:ozon-st.cdn.ngenix.net",
    "domain:wildberries.ru",
    "domain:wb.ru",
    "domain:wbstatic.net",
    "domain:wbbasket.ru",
    "domain:wbx-content.ru",
    "domain:avito.ru",
    "domain:avito.st",
    "domain:megamarket.ru",
    "domain:sbermegamarket.ru",
    "domain:gosuslugi.ru",
    "domain:vkusvill.ru",
    "domain:tinkoff.ru",
    "domain:nalog.gov.ru",
    "domain:mos.ru",
    "domain:2gis.com",
    "domain:2gis.ru",
    "geosite:category-ru",
]


def _selection(links: list[str], exclude_hosts: frozenset[str] | set[str]) -> list[str]:
    """По одной записи на адрес и первый Hysteria2 — без нашего потолка в пять."""
    chosen: list[str] = []
    seen: set[str] = set()
    hysteria: str | None = None
    for uri in links:
        parsed = _parse_uri(uri)
        if parsed is None:
            continue
        scheme, _, host, _, _, _ = parsed
        if host in exclude_hosts:
            continue
        if scheme in ("hysteria2", "hy2"):
            hysteria = hysteria or uri
            continue
        if host not in seen:
            seen.add(host)
            chosen.append(uri)
    return chosen + ([hysteria] if hysteria else [])


def _outbound_tag(index: int) -> str:
    # Как у них: r, r-2, r-3…
    return _OUTBOUND_PREFIX if index == 0 else f"{_OUTBOUND_PREFIX}-{index + 1}"


def _as_theirs(outbound: dict) -> dict:
    if outbound["protocol"] != "hysteria":
        return outbound
    stream = outbound["streamSettings"]
    tls = {**stream["tlsSettings"], "fingerprint": "chrome"}
    return {
        **outbound,
        "streamSettings": {**stream, "tlsSettings": tls, "finalmask": {"quicParams": dict(_QUIC_PARAMS)}},
    }


def build_test_config(
    links: list[str], *, exclude_hosts: frozenset[str] | set[str] = frozenset()
) -> dict | None:
    """Одна запись — автовыбор с настройками конкурента. None, если серверов нет."""
    outbounds: list[dict] = []
    for uri in _selection(links, exclude_hosts):
        outbound = build_outbound(uri, _outbound_tag(len(outbounds)))
        if outbound is not None:
            outbounds.append(_as_theirs(outbound))
    if not outbounds:
        return None
    balancer = {"balancerTag": _BALANCER_TAG}
    return {
        "remarks": TEST_REMARKS,
        "log": {"loglevel": "warning"},
        "dns": _DNS,
        "inbounds": _INBOUNDS,
        "outbounds": [
            *outbounds,
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainMatcher": "hybrid",
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"},
                {"type": "field", "domain": list(_IP_CHECK_DOMAINS), **balancer},
                {"type": "field", "domain": list(_DIRECT_DOMAINS), "outboundTag": "direct"},
                {"type": "field", "network": "tcp,udp", **balancer},
            ],
            "balancers": [
                {
                    "tag": _BALANCER_TAG,
                    "selector": [_OUTBOUND_PREFIX],
                    "strategy": _STRATEGY,
                    "fallbackTag": "direct",
                }
            ],
        },
        "burstObservatory": _BURST_OBSERVATORY,
    }


# «🇪🇺 Мост 🇷🇺 ➡️ 🇪🇺» Phantom (снят 24.09.2026): один сервер — вход в России
# (Санкт-Петербург, Reality на 443 со своим доменом), выход в Германии. У нас
# то же самое — каскад Москва → Франкфурт, поэтому копируется клиентская часть:
# весь трафик в туннель без деления на российское и зарубежное (российское
# выходит из моста, а не с телефона), торренты напрямую, DNS 1.1.1.1/1.0.0.1.
BRIDGE_REMARKS = "🧪 Тест · мост как у Phantom 🇷🇺 ➡️ 🇩🇪"
_BRIDGE_DNS = {"queryStrategy": "UseIP", "servers": ["1.1.1.1", "1.0.0.1"]}


def build_bridge_test_config(uri: str | None) -> dict | None:
    """Одна запись — мост с настройками конкурента поверх нашего каскада."""
    outbound = build_outbound(uri, "proxy") if uri else None
    if outbound is None:
        return None
    return {
        "remarks": BRIDGE_REMARKS,
        "log": {"loglevel": "warning"},
        "dns": _BRIDGE_DNS,
        "inbounds": _INBOUNDS,
        "outbounds": [
            outbound,
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        # Правило одно; всё остальное уходит в первый выход — мост.
        "routing": {
            "domainMatcher": "hybrid",
            "domainStrategy": "IPIfNonMatch",
            "rules": [{"type": "field", "protocol": ["bittorrent"], "outboundTag": "direct"}],
        },
    }
