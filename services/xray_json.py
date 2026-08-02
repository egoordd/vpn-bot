"""Build Xray-JSON subscription entries from proxy URIs.

Some clients (Happ, v2rayN, Streisand) accept a subscription whose body is a
JSON array of full xray-core configs instead of a base64 list of `scheme://`
URIs — each array element is a complete config the client runs 1:1. That lets
us ship an **«⚡️ Авто-обход»** entry: a single config with an observatory that
pings every server and a routing balancer (`leastPing`) that sends traffic
through the fastest live one and re-routes on the fly when it degrades — the
"tap once, always works" server the non-technical user wants.

Only xray-core protocols (VLESS, Trojan) go into these configs; Hysteria2 runs
on a different core in Happ and cannot live inside an xray balancer, so it is
skipped here (the plain base64 subscription still carries it).

Pure functions, stdlib only — mirrors the gateway it feeds.
"""
from __future__ import annotations

import json
import os
import urllib.parse

# Standard local inbounds an xray-json client bridges its TUN to (socks + http).
# Ports per the XTLS JSON-subscription convention (10808/10809).
_INBOUNDS = [
    {
        "tag": "socks-in",
        "listen": "127.0.0.1",
        "port": 10808,
        "protocol": "socks",
        "settings": {"udp": True, "auth": "noauth"},
        "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
    },
    {
        "tag": "http-in",
        "listen": "127.0.0.1",
        "port": 10809,
        "protocol": "http",
        # Same sniffing as the socks inbound: routing decides on names, so an
        # inbound that cannot recover the name would send everything through
        # the catch-all — including Russian services that belong direct.
        "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
    },
]

# Plain http:// on purpose: the observatory measures a server's latency by
# fetching this, and an https:// probe adds a full TLS handshake to gstatic
# *inside* the tunnel to every measurement. That inflates each reading by a
# round-trip or three on a throttled RU link and distorts which server
# leastPing considers fastest. 204-generators are served over HTTP for exactly
# this reason.
_PROBE_URL = "http://www.gstatic.com/generate_204"
# Failover speed: this interval *is* the outage a user sits through, because a
# balancer can only route around a server once a fresh probe has judged it. The
# old 3m let a node black-hole traffic for three minutes — "connected but
# nothing loads", switch by hand.
#
# 15s was the first correction and overshot: a probe round dials *every* proxy,
# so with a location per entry that is a burst of tunnel setups four times a
# minute, running forever in the background. On a phone that reads as an app
# that never idles, which is what battery optimisers kill — and a killed app is
# itself reported as "the VPN disconnects on its own". 60s still detects a dead
# node three times faster than the original while leaving the client mostly
# quiet.
_PROBE_INTERVAL = "60s"
_PROBE_TIMEOUT = "4s"
# Samples kept per server: the strategy judges on the recent window, so a node
# that degrades (rather than dies outright) is demoted after a couple of bad
# samples instead of staying selected on one stale good reading.
_PROBE_SAMPLING = 3
# A server slower than this is treated as unusable, which is what makes
# "switches when a server just gets slow" work at all — pure latency ranking
# keeps picking the least-bad node even when every reading is terrible.
_MAX_RTT = "4s"

# leastPing ranks purely on measured latency, which is exactly what a user
# feels: a node that merely gets slow sinks in the ranking on the next probe
# and stops being picked, so short _PROBE_INTERVAL covers both "died" and
# "долго грузит". leastLoad optimises for *stability* instead and measurably
# picked worse servers here — benchmarked from a real RU line 2026-07-28,
# leastPing 295/421ms via Frankfurt vs leastLoad 465/616ms via Amsterdam — so
# it stays available (BALANCER_STRATEGY=leastload) but is not the default.
BALANCER_STRATEGY = os.environ.get("BALANCER_STRATEGY", "leastping").strip().lower()

AUTO_REMARKS = "⚡️ Авто-обход"

# Resolver the client answers app lookups with. Routing no longer needs it —
# every rule matches on the name (`AsIs`) — but the app still has to turn a
# name into an address before it can open anything, and that is where this has
# broken twice.
#
# Nothing here may be `localhost`, for two independent reasons:
#
#   1. The device's resolver is the carrier's, and it does not answer for
#      blocked names at all — measured 2026-07-29 from an MTS line: tiktok.com,
#      instagram.com, cdninstagram.com and tiktokcdn.com all came back empty
#      while 1.1.1.1 resolved every one. With no address the app never opens a
#      connection, so sniffing has nothing to recover and the tunnel never sees
#      the request: YouTube, Spotify and Google simply fail while everything
#      unblocked keeps working, and the VPN looks connected and broken at once.
#   2. In TUN mode the VPN owns the system resolver, so `localhost` asks the OS,
#      which asks the client, which asks xray — the lookup loop that took the
#      whole client down on 2026-07-28.
#
# Both are avoided by naming resolvers as addresses, never as the system: xray
# generates these queries itself and routes them by its own rules, so the OS is
# never involved. Foreign resolvers ride the tunnel (the balancer, so a dead
# node cannot wedge lookups), while Russian names go to a Russian resolver that
# routes direct by geoip:ru — RU sites keep resolving to their nearby CDN and
# keep working, which is the whole point of the RU-split.
_RU_RESOLVER = "77.88.8.8"        # Yandex, inside RU — direct by geoip:ru
_FOREIGN_RESOLVERS = ["1.1.1.1", "8.8.8.8"]

# Russian destinations that must leave the device directly, matched by NAME so
# no lookup is needed to decide. The regexps cover the national zones in one
# line each; the rest are the RU services that live outside them.
_RU_DIRECT_DOMAINS = [
    "regexp:\\.ru$",
    "regexp:\\.su$",
    "regexp:\\.xn--p1ai$",  # .рф
    "domain:vk.com",
    "domain:vk.me",
    "domain:userapi.com",
    "domain:mycdn.me",
    "domain:yandex.net",
    "domain:yandex.com",
    "domain:ozon.com",
    "domain:wildberries.com",
    "domain:gosuslugi.gov",
    # Russian services that do NOT live in a Russian zone. Measured on
    # 2026-08-03 by reading xray's own routing decisions: every one of these was
    # being sent abroad, which is what «РУ-приложения работают не всегда» is —
    # Sber and Gosuslugi are `.ru` and worked, while Yandex lost its stylesheets,
    # Avito lost its images and Okko refused to play at all.
    "domain:yastatic.net",      # every Yandex page pulls its CSS/JS from here
    "domain:yastat.net",
    "domain:yandexcloud.net",   # backend of a great many Russian apps
    "domain:avito.st",          # Avito's image CDN
    "domain:vk-cdn.net",
    "domain:vkuservideo.net",
    "domain:vkuseraudio.net",
    "domain:vkuseraudio.com",
    "domain:mradx.net",         # Mail.ru
    "domain:my.games",
    "domain:okko.tv",           # refuses foreign addresses outright
    "domain:more.tv",
    "domain:premier.one",
    "domain:wbstatic.net",
    "domain:sberbank.com",
    "domain:yoomoney.ru",
    "domain:qiwi.com",
    "domain:2gis.com",
    "domain:tamtam.chat",
]

_DNS = {
    "servers": [
        # Scoped first: RU names are answered by a RU resolver, whose reply
        # routes direct anyway, so domestic CDNs stay domestic.
        {"address": _RU_RESOLVER, "domains": _RU_DIRECT_DOMAINS},
        *_FOREIGN_RESOLVERS,
    ],
    # The exits are IPv4-only. An AAAA answer sends the app to an address the
    # exit cannot reach, and dual-stack is exactly what the big platforms
    # publish — so ask for A records only.
    "queryStrategy": "UseIPv4",
}

# Domains that must never take the geoip:ru direct path, whatever their address
# resolves to.
#
# This is the sharp edge of the RU-split feature. Sending `geoip:ru` straight
# out of the device is right for banks and gosuslugi, but every one of these
# platforms is blocked or throttled in RU *and* keeps CDN capacity inside the
# country — YouTube most of all, whose Google Global Cache nodes sit in Russian
# ISPs. A lookup landing on one of those returns a Russian address, geoip:ru
# then routes it out of the device, and the request arrives at an edge that is
# frozen (TikTok has served no new RU content since 2022), filtered, or
# deliberately throttled. The user sees stale feeds and crawling video rather
# than an error — the VPN looks connected and broken at the same time, which is
# exactly what was reported and what competitors without RU-split don't suffer.
#
# Matching on the domain, ahead of every IP rule, decides before an address is
# even known, so no CDN placement can undo it.
_FORCE_PROXY_DOMAINS = [
    # TikTok / ByteDance
    "domain:tiktok.com",
    "domain:tiktokcdn.com",
    "domain:tiktokcdn-us.com",
    "domain:tiktokcdn-eu.com",
    "domain:tiktokcdn-in.com",
    "domain:tiktokv.com",
    "domain:tiktokv.us",
    "domain:ttlivecdn.com",
    "domain:ttwstatic.com",
    "domain:byteoversea.com",
    "domain:byteicdn.com",
    "domain:bytedance.com",
    "domain:bytedapm.com",
    "domain:ibytedtos.com",
    "domain:ipstatp.com",
    "domain:sgpstatp.com",
    "domain:snssdk.com",
    "domain:isnssdk.com",
    "domain:muscdn.com",
    "domain:musical.ly",
    "domain:capcut.com",
    # Meta
    "domain:instagram.com",
    "domain:cdninstagram.com",
    "domain:fbcdn.net",
    "domain:facebook.com",
    "domain:fb.com",
    "domain:threads.net",
    "domain:whatsapp.com",
    "domain:whatsapp.net",
    # YouTube / Google video — googlevideo.com is the throttled one, and its
    # cache nodes are physically inside RU networks.
    "domain:youtube.com",
    "domain:youtu.be",
    "domain:googlevideo.com",
    "domain:ytimg.com",
    "domain:ggpht.com",
    "domain:youtubei.googleapis.com",
    # Google proper. Not optional once addresses decide routing (below): Google
    # Global Cache sits inside Russian ISPs, so google.com resolves to a Russian
    # address for a Russian client, `geoip:ru` would send it out of the device,
    # and it arrives at an edge that is throttled. Search and Photos are what
    # the user notices.
    "domain:google.com",
    "domain:gstatic.com",
    "domain:googleapis.com",
    "domain:googleusercontent.com",
    "domain:withgoogle.com",
    "domain:google-analytics.com",
    # Spotify left Russia and refuses Russian addresses, so it must never take
    # the direct path — including its Fastly/Akamai edges, which do sit in RU.
    "domain:spotify.com",
    "domain:spotifycdn.com",
    "domain:scdn.co",
    "domain:spotify.map.fastly.net",
    "domain:audio-ak-spotify-com.akamaized.net",
    # Other blocked platforms with RU-facing infrastructure
    "domain:twitter.com",
    "domain:x.com",
    "domain:twimg.com",
    "domain:discord.com",
    "domain:discordapp.com",
    "domain:discord.gg",
]


def _tail_outbounds() -> list[dict]:
    return [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block", "protocol": "blackhole"},
        # Answers lookups from the `dns` block above instead of letting them
        # reach whatever resolver the app addressed. Without it the settings
        # above only apply when the client happens to hijack DNS itself, and on
        # a client that does not, every lookup still goes to the carrier — which
        # is the failure being fixed.
        {"tag": "dns-out", "protocol": "dns"},
    ]


# Send Russian destinations straight out the device (real local IP) instead of
# tunnelling them to a foreign exit and back: RU banks / gosuslugi / apps then
# see a Russian IP and work, and RU traffic — most of a user's day — takes zero
# VPN detour, which is the biggest lever on felt latency.
#
# Names decide first, addresses decide what is left. `AsIs` alone was measured
# on 2026-08-03 to leave the `geoip:ru` rule dead: sniffing replaces the target
# address with the domain, and with no resolution an IP rule can never match, so
# every Russian service outside a `.ru` zone was riding the tunnel — Yandex's
# static host, Avito's images, VK's CDN, Okko. A name list alone cannot fix that;
# it can only ever cover what someone remembered to add.
#
# `IPIfNonMatch` resolves *only* what no name rule has already decided, so both
# earlier outages stay avoided:
#   - the tunnel-wedge (2026-07-2x): failover is driven by the balancer's own
#     probes, not by lookups, and a lookup that fails simply leaves the rule
#     unmatched and falls through — it cannot hang the client;
#   - the phone loop (2026-07-28): lookups are answered by `dns-out` inside
#     xray and never handed to the system resolver.
# The resolution is also nearly free: the app's own lookup already went through
# `dns-out`, so the routing lookup hits xray's cache.
def _split_routing(final_rule: dict) -> dict:
    # Whatever `final_rule` sends traffic to (a single proxy outbound, or the
    # balancer) is where the pinned domains must go too.
    destination = {
        key: value for key, value in final_rule.items() if key in ("outboundTag", "balancerTag")
    }
    return {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            # Every lookup the apps make, whatever resolver they addressed, is
            # answered by our `dns` block. Scoped to the local inbounds on
            # purpose: the queries xray's own resolver then sends to 1.1.1.1
            # arrive without an inbound tag, so they fall through to the rules
            # below and ride the tunnel instead of matching this rule again —
            # which would be an endless loop. The 2026-07-28 outage was the
            # other shape of this: port 53 sent *direct* left the device, the
            # VPN owned the system resolver, and the query came straight back
            # in.
            {
                "type": "field",
                "inboundTag": ["socks-in", "http-in"],
                "port": 53,
                "outboundTag": "dns-out",
            },
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
            # Russian names are settled before QUIC is refused below, so
            # domestic services — VK video, Yandex, Kinopoisk — keep using it.
            # They never touch the tunnel, so the reason for refusing it does
            # not apply to them, and taking QUIC away would only make them
            # slower. None of these names appear in the pinned list below, so
            # deciding them early cannot divert a blocked platform (there is a
            # test for that).
            {"type": "field", "domain": _RU_DIRECT_DOMAINS, "outboundTag": "direct"},
            # QUIC is refused for everything still undecided — that is, for
            # everything bound for the tunnel — so those applications fall back
            # to TLS over TCP.
            #
            # This is the "«works, then photos and videos stop loading» while
            # the balancer stays silent" case. QUIC is UDP, and a UDP flow
            # inside a TCP tunnel is TCP-over-TCP: both layers retransmit, and
            # on a lossy mobile link the inner and outer windows fight each
            # other until throughput collapses, which takes a while to build up
            # — hence "after a long session". Media is what breaks first
            # because photos and video are exactly what YouTube, Instagram,
            # Google Photos and Spotify move over QUIC, while ordinary pages
            # keep working over TCP.
            #
            # The balancer cannot see any of it: its probe is a small HTTP
            # fetch over TCP, which stays fast on a link whose UDP path is
            # melting, so no node ever looks unhealthy and nothing switches.
            # Refusing QUIC outright is what makes the applications themselves
            # fall back — they do it in one round trip and never come back to
            # it for that connection.
            {"type": "field", "network": "udp", "port": 443, "outboundTag": "block"},
            # Blocked platforms: they must reach the tunnel even though some of
            # their CDN sits on Russian addresses, so they are pinned by name
            # ahead of the address rule below.
            {"type": "field", "domain": _FORCE_PROXY_DOMAINS, **destination},
            # Catches Russian services this list never named, now that
            # IPIfNonMatch gives the rule an address to work with.
            {"type": "field", "ip": ["geoip:ru"], "outboundTag": "direct"},
            final_rule,
        ],
    }


def _parse_uri(uri: str) -> tuple[str, str, str, int, dict, str] | None:
    """Split a proxy URI into (scheme, userinfo, host, port, query, remark).

    Returns None when the URI isn't a parseable `scheme://userinfo@host:port`.
    """
    if "://" not in uri:
        return None
    scheme, rest = uri.split("://", 1)
    if "@" not in rest:
        return None
    userinfo, after_at = rest.split("@", 1)
    hostportq, _, fragment = after_at.partition("#")
    hostport, _, query_str = hostportq.partition("?")
    host = hostport.split(":", 1)[0]
    if not host:
        return None
    port = 443
    if ":" in hostport:
        try:
            port = int(hostport.rsplit(":", 1)[1])
        except ValueError:
            return None
    query = {k: v[0] for k, v in urllib.parse.parse_qs(query_str, keep_blank_values=True).items()}
    remark = urllib.parse.unquote(fragment) if fragment else host
    return scheme.lower(), userinfo, host, port, query, remark


# Client-side TCP keepalive: a carrier CGNAT drops an idle tunnel mapping at
# ~15-30min, leaving the connection half-open («подключён, но не грузит»).
# Probing every ~25s (after 30s idle) keeps the mapping fresh from the outbound
# direction — the server inbounds carry the same option for the return path.
_KEEPALIVE_SOCKOPT = {"tcpKeepAliveIdle": 30, "tcpKeepAliveInterval": 25}


def _xhttp_settings(query: dict) -> dict:
    """Transport block for an XHTTP link.

    XHTTP carries the tunnel inside ordinary HTTP requests, which survives DPI
    that recognises and kills a raw TLS-shaped stream — the transport a client
    falls back to when Reality-over-TCP stops connecting. Without this block the
    JSON config would name the network but omit its path, and the connection
    would fail; the panel puts the tuning knobs in `extra` as JSON.
    """
    settings: dict = {"path": query.get("path", "/"), "mode": query.get("mode", "auto")}
    host = query.get("host", "")
    if host:
        settings["host"] = host
    extra = query.get("extra", "")
    if extra:
        try:
            parsed = json.loads(extra)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            settings["extra"] = parsed
    return settings


def _stream_settings(query: dict) -> dict:
    network = query.get("type", "tcp") or "tcp"
    security = query.get("security", "none") or "none"
    stream: dict = {"network": network, "security": security, "sockopt": dict(_KEEPALIVE_SOCKOPT)}
    if network == "xhttp":
        stream["xhttpSettings"] = _xhttp_settings(query)
    sni = query.get("sni") or query.get("host") or ""
    fingerprint = query.get("fp", "")
    if security == "reality":
        reality = {
            "serverName": sni,
            "publicKey": query.get("pbk", ""),
            "shortId": query.get("sid", ""),
            "spiderX": query.get("spx", ""),
        }
        if fingerprint:
            reality["fingerprint"] = fingerprint
        stream["realitySettings"] = reality
    elif security == "tls":
        tls: dict = {"serverName": sni}
        if fingerprint:
            tls["fingerprint"] = fingerprint
        stream["tlsSettings"] = tls
    return stream


def build_outbound(uri: str, tag: str) -> dict | None:
    """Map one VLESS/Trojan URI to an xray outbound. None for anything else."""
    parsed = _parse_uri(uri)
    if parsed is None:
        return None
    scheme, userinfo, host, port, query, _ = parsed

    if scheme == "vless":
        user: dict = {"id": userinfo, "encryption": query.get("encryption", "none") or "none"}
        flow = query.get("flow")
        if flow:
            user["flow"] = flow
        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
            "streamSettings": _stream_settings(query),
        }
    if scheme == "trojan":
        return {
            "tag": tag,
            "protocol": "trojan",
            "settings": {"servers": [{"address": host, "port": port, "password": userinfo}]},
            "streamSettings": _stream_settings(query),
        }
    return None


def _remark(uri: str, fallback: str) -> str:
    parsed = _parse_uri(uri)
    return parsed[5] if parsed else fallback


def build_server_config(uri: str, tag_index: int) -> dict | None:
    """A standalone single-server xray config (so the user can still pick one)."""
    outbound = build_outbound(uri, "proxy")
    if outbound is None:
        return None
    return {
        "remarks": _remark(uri, f"Сервер {tag_index + 1}"),
        "log": {"loglevel": "warning"},
        "dns": _DNS,
        "inbounds": _INBOUNDS,
        "outbounds": [outbound, *_tail_outbounds()],
        "routing": _split_routing(
            {"type": "field", "network": "tcp,udp", "outboundTag": "proxy"}
        ),
    }


def _health_check(strategy: str) -> tuple[dict, dict]:
    """(balancer strategy, health-probe block) for the configured strategy.

    leastLoad needs `burstObservatory` (rolling samples + a timeout), leastPing
    needs the plain `observatory`; the two are not interchangeable, so the pair
    is built together to keep them consistent.
    """
    if strategy != "leastload":
        return (
            {"type": "leastPing"},
            {
                "observatory": {
                    "subjectSelector": ["proxy-"],
                    "probeUrl": _PROBE_URL,
                    "probeInterval": _PROBE_INTERVAL,
                    "enableConcurrency": True,
                }
            },
        )
    return (
        # `expected: 2` keeps a second healthy server in play instead of pinning
        # every connection to a single "best" one, so one node degrading never
        # takes the whole session down with it.
        {"type": "leastLoad", "settings": {"expected": 2, "maxRTT": _MAX_RTT, "tolerance": 0.3}},
        {
            "burstObservatory": {
                "subjectSelector": ["proxy-"],
                "pingConfig": {
                    "destination": _PROBE_URL,
                    "interval": _PROBE_INTERVAL,
                    "timeout": _PROBE_TIMEOUT,
                    "sampling": _PROBE_SAMPLING,
                },
            }
        },
    )


def build_balancer_config(uris: list[str], remarks: str = AUTO_REMARKS) -> dict | None:
    """A single config that balances across every server, healthiest first.

    A health prober samples each `proxy-*` outbound continuously; the balancer
    routes each connection through a server that is currently fast, and demotes
    one that dies *or merely gets slow* (see _MAX_RTT) without the user
    touching anything. None when no xray-core outbound could be built.
    """
    outbounds: list[dict] = []
    for uri in uris:
        outbound = build_outbound(uri, f"proxy-{len(outbounds)}")
        if outbound is not None:
            outbounds.append(outbound)
    if not outbounds:
        return None
    strategy, prober = _health_check(BALANCER_STRATEGY)
    return {
        "remarks": remarks,
        "log": {"loglevel": "warning"},
        "dns": _DNS,
        "inbounds": _INBOUNDS,
        "outbounds": [*outbounds, *_tail_outbounds()],
        "routing": {
            **_split_routing({"type": "field", "network": "tcp,udp", "balancerTag": "auto"}),
            "balancers": [{"tag": "auto", "selector": ["proxy-"], "strategy": strategy}],
        },
        **prober,
    }


def build_json_subscription(links: list[str]) -> list[dict]:
    """Full JSON-array body: the balancer first, then each server on its own.

    Objects only: mixing raw URI strings into the array broke Happ's import
    outright («there are no server links», verified live 2026-07-16), so
    non-xray protocols (Hysteria2 — separate core) simply cannot ride in this
    format and are left to the base64 flavor other clients receive.

    Empty when no xray-core-compatible server is present (caller then falls
    back to the plain base64 subscription).
    """
    balancer = build_balancer_config(links)
    if balancer is None:
        return []
    configs = [balancer]
    for index, uri in enumerate(links):
        server = build_server_config(uri, index)
        if server is not None:
            configs.append(server)
    return configs
