#!/usr/bin/env python3
"""Multi-protocol subscription gateway.

Wraps the Marzban subscription: fetches the user's proxy links from the panel
(token-authed, so it's per-user and respects status/expiry) and appends a
Hysteria2 entry for each location the user has. Every link Marzban issues is
passed through verbatim, so adding a panel-side inbound (VLESS Reality, Trojan,
…) surfaces it in the subscription without changing this gateway. The client
imports ONE link and sees all protocols per location, e.g. 🇺🇸 США VLESS +
Trojan + Hysteria2, 🇳🇱 Нидерланды VLESS + Trojan + Hysteria2.

Runs on the main server next to Marzban. Stdlib only (no pip deps).

Env:
  MARZBAN_BASE   e.g. https://panel.23.95.3.18.sslip.io
  US_HY2_PASS    Hysteria2 password on the US node
  NL_HY2_PASS    Hysteria2 password on the NL node
  LISTEN_PORT    default 8090 (bind 127.0.0.1; nginx proxies a public path)
"""
from __future__ import annotations

import base64
import functools
import html
import json
import os
import re
import socket
import sqlite3
import ssl
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# In the repo this is the services package; on the VPS the gateway runs
# standalone as /opt/sub_gateway.py with /opt/xray_json.py beside it (the
# script's own dir is on sys.path), so fall back to a flat import.
try:
    from services.xray_json import build_json_subscription
except ImportError:  # pragma: no cover - standalone deploy path
    from xray_json import build_json_subscription

MARZBAN_BASE = os.environ.get("MARZBAN_BASE", "https://panel.23.95.3.18.sslip.io").rstrip("/")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8090"))
BIND_HOST = os.environ.get("BIND_HOST", "127.0.0.1")
CERT_FILE = os.environ.get("CERT_FILE", "")  # when set -> serve HTTPS on BIND_HOST
KEY_FILE = os.environ.get("KEY_FILE", "")
# Public origin used to build the /sub/<token> URL embedded in the Happ deep
# link. Empty -> derive from the request Host header (correct in prod).
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "").rstrip("/")
# When set, a browser opening /sub/<token> is redirected to this site's
# /connect page (VPN clients still get the raw config). Empty -> disabled.
CONNECT_PAGE_BASE = os.environ.get("CONNECT_PAGE_BASE", "").rstrip("/")

# Substrings that identify a VPN/proxy client User-Agent — these must always
# receive the raw subscription, never the HTML redirect.
_VPN_CLIENT_UA = (
    "v2rayng", "v2raytun", "v2box", "happ", "hiddify", "streisand", "clash",
    "mihomo", "sing-box", "singbox", "nekobox", "nekoray", "shadowrocket",
    "foxray", "karing", "throne", "matsuri", "sagernet", "exclave", "loon",
    "surge", "stash", "quantumult", "flclash", "xray", "v2ray", "wings",
    "sub-store", "subconverter",
)


def _is_browser(user_agent: str) -> bool:
    """Conservative browser check: only true for a clear browser UA that is not
    a known VPN client. Fails safe — an unknown/empty UA is treated as a client
    and gets the raw subscription, never a redirect."""
    ua = (user_agent or "").lower()
    if not ua or any(client in ua for client in _VPN_CLIENT_UA):
        return False
    return "mozilla" in ua


# Clients that accept an xray-JSON array body (a list of whole xray configs)
# instead of the base64 URI list. Only they can be served the «⚡️ Авто-обход»
# balancer inside the plain subscription: a balancer is an entire config and
# cannot be expressed as a `scheme://` URI, so a base64-only client would
# silently lose it. Happ is the app we ship and its JSON handling is verified
# live on the /auto flavor. AUTO_IN_SUB switches the behaviour off without a
# code deploy if a client turns out to choke on it.
AUTO_IN_SUB = os.environ.get("AUTO_IN_SUB", "1").lower() not in ("0", "false", "no", "")


def _json_clients(raw: str) -> tuple[str, ...]:
    """Список приложений из настройки: «happ, incy» → ("happ", "incy")."""

    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


# У конкурента «Авто-обход» работает и в INCY, у нас — только в Happ, и людям
# это видно. Проверить чужое приложение можно лишь на настоящей установке,
# поэтому список вынесен в настройку XRAY_JSON_UA: добавили `incy`, попробовали
# на живом телефоне, не понравилось — убрали строку, без выкладки кода. Отдать
# JSON тому, кто его не разбирает, нельзя молча: человек останется вообще без
# серверов, а выглядеть это будет как сломанная подписка.
_XRAY_JSON_UA = _json_clients(os.environ.get("XRAY_JSON_UA", "happ"))


def _supports_xray_json(user_agent: str) -> bool:
    """True for clients known to parse an xray-JSON array subscription."""
    ua = (user_agent or "").lower()
    return any(client in ua for client in _XRAY_JSON_UA)


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# Display name clients show for the subscription (Happ reads `profile-title`,
# base64 UTF-8, max 25 chars). Without it Happ shows the default "subscription".
SUB_TITLE = os.environ.get("SUB_TITLE", "UnLock VPN")
PROFILE_TITLE_HEADER = "base64:" + base64.b64encode(SUB_TITLE.encode("utf-8")).decode("ascii")

# Announcement shown above the server list in Happ (max 200 chars). It answers
# the one question that otherwise becomes a support ticket — "connected but a
# site won't open" — with the fix the user can apply themselves, and carries
# the referral offer to the audience most likely to act on it. HTTP headers are
# latin-1 only, so Cyrillic must ride as base64, which Happ decodes.
SUB_ANNOUNCE = os.environ.get(
    "SUB_ANNOUNCE",
    "⚡️ Авто-обход — обычный режим\n"
    "🇷🇺 Режим РУ-сервисов — если банк или Госуслуги ругаются на VPN\n"
    "❗️ Не грузит? Обновите (↻), затем ⏱ и выберите сервер с меньшим ms\n"
    "🎁 Друг по вашей ссылке — 20% с его оплат",
)
# Buttons Happ renders next to the subscription.
SUPPORT_URL = os.environ.get("SUB_SUPPORT_URL", "https://t.me/unlock_support_bot")
PROFILE_WEB_PAGE_URL = os.environ.get("SUB_WEB_PAGE_URL", "https://unlockproject.site")

# Happ "advanced" parameters. They only apply when `providerid` rides along, and
# they are what turns a filtered domain from an outage into something nobody
# notices:
#   new-url      the app replaces its stored subscription address with this one
#                on the next refresh, so every install that can still reach the
#                old host migrates itself within the hour. The whole address, not
#                Happ's `new-domain` host swap: old links also live on :8444 and
#                :8446, and a swap keeps the port, pointing them at nothing;
#   fallback-url the app stores it and switches over on its own once the primary
#                stops answering (no reply in 9s, or HTTP 300-599) — which is
#                exactly how a name-filtered host fails.
# Kept on a domain-independent host so one blocklist entry cannot take out both.
HAPP_PROVIDER_ID = os.environ.get("HAPP_PROVIDER_ID", "")
# Where installs are moved to: scheme and host of the working subscription
# address, e.g. https://unlockru.site.
SUB_NEW_BASE = os.environ.get("SUB_NEW_BASE", "")
SUB_FALLBACK_BASE = os.environ.get("SUB_FALLBACK_BASE", "")
# Who is told to move. `new-url` rewrites an install for good, so it goes to a
# named test group first: comma-separated panel usernames, or "*" for everyone.
# Empty means nobody — a target address on its own never migrates a single user.
SUB_MIGRATE_USERS = frozenset(
    name.strip() for name in os.environ.get("SUB_MIGRATE_USERS", "").split(",") if name.strip()
)


# Settings we apply on the user's behalf. The product promise is pay, tap once,
# done — so anything that would otherwise be "go into settings and turn this on"
# has to be shipped with the subscription instead. Happ applies these on every
# refresh; other clients ignore unknown headers.
APP_HEADERS = {
    # Reconnect by itself when the app comes up, to whatever was last used.
    # Covers the case that started this: the phone slept, the system reclaimed
    # the tunnel, and nothing worked until the app was opened by hand.
    "subscription-autoconnect": "true",
    "subscription-autoconnect-type": "lastused",
    # Android: come back after a reboot instead of staying off until noticed.
    "app-auto-start": "true",
    # Pull the subscription on every launch, so a fix does not wait out the
    # refresh interval on a phone that was off.
    "subscription-auto-update-open-enable": "true",
    # iOS: keep Apple's push service outside the tunnel. Notifications then
    # arrive even when the tunnel is down — the user still gets their Telegram
    # messages instead of a silent phone — and the tunnel carries less.
    "exclude-apns-enable": "true",
}


def _token_username(token: str) -> str | None:
    """Panel username inside a Marzban token, unverified.

    The token is base64 of `<username>,<issued-at>` with the signature appended
    raw, so only its longest decodable prefix carries the name. Good enough to
    pick a test group; never an authorisation decision.
    """
    if not token or len(token) > 256:
        return None
    for length in range(len(token), 7, -1):
        if length % 4 == 1:
            continue
        try:
            decoded = base64.urlsafe_b64decode(token[:length] + "===")
        except Exception:
            continue
        name = decoded.decode("utf-8", "replace").split(",", 1)[0].strip()
        # corp_… — корпоративные учётные записи (см. CORP_USERS), заведены в панели
        # вручную, без аккаунта в боте.
        if re.fullmatch(r"tg_-?\d{1,20}|corp_[a-z0-9_]{1,24}", name):
            return name
    return None


def _migrates(token: str | None) -> bool:
    if not SUB_NEW_BASE or not token or not SUB_MIGRATE_USERS:
        return False
    if "*" in SUB_MIGRATE_USERS:
        return True
    return _token_username(token) in SUB_MIGRATE_USERS


def _client_headers(token: str | None = None, flavor: str = "") -> dict[str, str]:
    """Presentation headers every subscription response carries."""
    headers = {"profile-title": PROFILE_TITLE_HEADER, **APP_HEADERS}
    if HAPP_PROVIDER_ID:
        headers["providerid"] = HAPP_PROVIDER_ID
        # Keep the flavor: moving or falling back must not silently downgrade a
        # user from /split (RU services direct) to the plain subscription.
        suffix = f"/{flavor}" if flavor else ""
        if _migrates(token):
            headers["new-url"] = f"{SUB_NEW_BASE.rstrip('/')}/sub/{token}{suffix}"
        if SUB_FALLBACK_BASE and token:
            headers["fallback-url"] = f"{SUB_FALLBACK_BASE.rstrip('/')}/sub/{token}{suffix}"
    if SUB_ANNOUNCE.strip():
        announce = SUB_ANNOUNCE.strip()[:200]
        headers["announce"] = "base64:" + base64.b64encode(
            announce.encode("utf-8")
        ).decode("ascii")
    if SUPPORT_URL:
        headers["support-url"] = SUPPORT_URL
    if PROFILE_WEB_PAGE_URL:
        headers["profile-web-page-url"] = PROFILE_WEB_PAGE_URL
    return headers

# vless host -> location + its Hysteria2 endpoint
NODES = {
    "172.86.119.133.sslip.io": {
        "flag": "🇺🇸", "name": "США",
        "hy2_host": "172.86.119.133.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("US_HY2_PASS", ""),
    },
    "107.189.22.160.sslip.io": {
        "flag": "🇳🇱", "name": "Нидерланды",
        "hy2_host": "107.189.22.160.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("NL_HY2_PASS", ""),
    },
    "78.17.154.225.sslip.io": {
        "flag": "🇵🇱", "name": "Польша",
        "hy2_host": "78.17.154.225.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("PL_HY2_PASS", ""),
        "trojan_port": 8444,
        "trojan_pass": os.environ.get("PL_TROJAN_PASS", ""),
    },
    "166.0.28.132.sslip.io": {
        "flag": "🇩🇪", "name": "Германия",
        "hy2_host": "166.0.28.132.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("DE_HY2_PASS", ""),
    },
}

# --- 🇷🇺→exit cascades ---------------------------------------------------------
# A domestic Moscow relay runs its own Xray (VLESS Reality) with split routing:
# it terminates the client's tunnel on a *Russian* IP (un-throttled first hop),
# then sends Russian destinations out its own Russian IP (geoip:ru / RU domains
# → direct, so banks / gosuslugi / RU apps see a Russian IP and work) and
# forwards everything else to a foreign exit (bypass). The relay listens on one
# port per exit country and routes that inbound to the matching exit node, so we
# offer a 🇷🇺→<country> cascade for every location. VLESS/TCP only — RU mobile
# blocks the UDP/QUIC path, so there is deliberately no Hysteria2 twin. Each
# entry is a standalone shared-secret link (like the Hy2/Trojan extras),
# hand-added below rather than derived from a per-user Marzban link. Expiry is
# still enforced upstream: resolve_links() blanks the whole sub for an expired
# user before this runs, so the cascade never leaks to a lapsed account here.
CASCADE_ENABLED = os.environ.get("CASCADE_ENABLED", "1").lower() not in ("0", "false", "no", "")
# The relay's own Reality identity (its keypair — the handshake terminates in
# Moscow), shared across every country port. Host == SNI == an sslip name
# resolving to the relay IP, per the SNI/IP-correlation fix for RU LTE.
RU_RELAY_HOST = os.environ.get("RU_RELAY_HOST", "130.49.143.41.sslip.io")
CASCADE_UUID = os.environ.get("CASCADE_UUID", "02ef44d5-0588-470f-a3e0-fdb498a3b501")
CASCADE_PBK = os.environ.get("CASCADE_PBK", "Z6NNgVuRJ2lFsgLLNv7aSMt-CS8Ywy5ZeZu898zoqno")
CASCADE_SID = os.environ.get("CASCADE_SID", "9a5e913a359a98a8")
# (relay port, remark) per exit country — mirrors the relay's per-country
# inbounds. These are the split-routing entries where RU sites/apps still work
# (RU traffic exits locally), so the label is the exit flag + a «РУ сервисы ✅»
# marker rather than the old «каскад» wording. Closest-first.
# Fastest first, and that ordering is load-bearing: «Авто-обход» takes one
# entry per host, every cascade shares the relay, so whichever sits first here
# is the cascade the balancer gets. Ordered by measurement from Moscow on
# 2026-08-04 — Frankfurt 114 Mbit/s against Warsaw's 75. Putting Poland first
# cost the automatic entry a third of its speed and was reported as "yesterday
# it was perfect, today it lags".
# (relay port, label, the exit it terminates on). The exit matters: a cascade
# is a tunnel to the relay *and onward*, so it is only as alive as the node it
# hands traffic to — see build_cascade_links.
# Order decides the load: «Авто-обход» keeps one entry per host, every cascade
# lives on the relay, so whichever country is first here is the one the balancer
# rides and the one listed first for anyone choosing by hand.
#
# Poland leads from 2026-08-22, reversing the 2026-08-04 order. That order was
# right when it was made — Frankfurt measured 114 Mbit/s against Warsaw's 75 —
# and putting Poland first back then cost a third of the throughput and drew
# "yesterday it was perfect, today it lags". Poland has since roughly doubled.
# Three 100 MB pulls from the Moscow relay through each exit:
#
#     Poland      145, 127, 153  ->  142 Mbit/s
#     Frankfurt   113, 137, 127  ->  126 Mbit/s
#     Amsterdam    82, 133,  55  ->   90 Mbit/s
#
# Frankfurt still wins on latency (37 ms against Poland's 67 from Moscow), but a
# cascade carries bulk traffic and its users have already accepted the Moscow
# detour, so throughput is what they feel. Amsterdam is both slowest and by far
# the least consistent, so it is not a candidate whatever its ping says.
#
# The load this moves is the point: Frankfurt was carrying 389 GB of the 554 we
# served in thirty days, and `cascade-de` alone accounted for 297 GB of it,
# climbing 24 GB a day. Poland has two idle cores and 3 GB free.
CASCADE_COUNTRIES = (
    (2091, "🇵🇱 Польша ✅ РУ сервисы", "78.17.154.225.sslip.io"),
    (2096, "🇩🇪 Германия ✅ РУ сервисы", "166.0.28.132.sslip.io"),
    # 🇳🇱 restored 2026-07-28 at the owner's call: it works from their vantage
    # point, which counts for more than one test line. Note it still measured
    # 1-3/10 from a Novosibirsk MTS line the same day, so if the silent
    # "connected but nothing loads" reports come back, this is the first
    # suspect — drop this line to pull it again.
    # 🇳🇱 pulled 2026-08-01: measured from a Russian line, every request the
    # balancer sent through Amsterdam failed while Poland and Germany served
    # the same seconds fine — that rotation is what users experienced as
    # "worked, then stopped". It answers TCP and TLS from both continents, so
    # nothing short of real traffic from Russia catches it.
    # Выход переехал 2026-08-31 на новую машину; здесь стоит адрес, по которому
    # health-пробер решает, показывать ли каскад, поэтому он должен совпадать с
    # тем, куда релей на самом деле форвардит.
    (2093, "🇺🇸 США ✅ РУ сервисы", "172.86.119.133.sslip.io"),
)

# The gateway calls our own Marzban panel (same host in prod), so TLS
# verification is unnecessary here and trips on the own-domain sslip cert.
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


# --- node health --------------------------------------------------------------
# Background TCP prober: every endpoint seen in a served subscription gets
# probed every HEALTH_INTERVAL seconds; after HEALTH_FAILS consecutive failures
# it is dropped from served configs until it answers again. Hysteria2/TUIC are
# UDP (no TCP probe possible) and inherit host-level health: dropped only when
# every TCP endpoint of that host is dead. If filtering would leave an empty
# config the unfiltered list is served — a broken prober must never wipe a
# paying user's subscription.
HEALTH_ENABLED = os.environ.get("HEALTH_ENABLED", "1").lower() not in ("0", "false", "")
HEALTH_INTERVAL = float(os.environ.get("HEALTH_INTERVAL", "45"))
HEALTH_TIMEOUT = float(os.environ.get("HEALTH_TIMEOUT", "3"))
HEALTH_FAILS = int(os.environ.get("HEALTH_FAILS", "2"))

_UDP_SCHEMES = ("hysteria2", "hy2", "tuic")
_health_lock = threading.Lock()
_probe_fails: dict[tuple[str, int], int] = {}  # (host, port) -> consecutive failures


def _uri_endpoint(uri: str) -> tuple[str, int] | None:
    host = _uri_host(uri)
    if not host:
        return None
    after_at = uri.split("@", 1)[1]
    hostport = after_at.split("?", 1)[0].split("/", 1)[0].split("#", 1)[0]
    port = 443
    if ":" in hostport:
        try:
            port = int(hostport.rsplit(":", 1)[1])
        except ValueError:
            return None
    return host, port


def _is_udp_uri(uri: str) -> bool:
    return uri.split("://", 1)[0].lower() in _UDP_SCHEMES


def _register_probe_targets(links: list[str]) -> None:
    with _health_lock:
        for uri in links:
            if _is_udp_uri(uri):
                continue
            endpoint = _uri_endpoint(uri)
            if endpoint and endpoint not in _probe_fails:
                _probe_fails[endpoint] = 0


# Verdicts from scripts/node_probe.py, which dials each node with xray and
# fetches a 204 through the tunnel. The in-process check below can only open a
# TCP socket, and a node that accepts connections then silently drops traffic
# passes that trivially — which is how Amsterdam stayed in every subscription
# while users sat on "connected but nothing loads". This file is the only
# signal that reflects bytes actually returning.
NODE_HEALTH_FILE = os.environ.get("NODE_HEALTH_FILE", "/run/unlock-node-health.json")
# Older than this and the prober is presumed broken, so its verdicts are
# ignored rather than trusted — a stalled prober must not strip a good node.
NODE_HEALTH_MAX_AGE = float(os.environ.get("NODE_HEALTH_MAX_AGE", "900"))


def _probed_dead_hosts() -> set[str]:
    """Hosts the end-to-end prober most recently found unable to pass traffic.

    Fails open on every error: an unreadable, malformed or stale file yields an
    empty set, so a prober problem can never blank a paying user's servers."""
    try:
        with open(NODE_HEALTH_FILE) as handle:
            payload = json.load(handle)
        checked_at = float(payload.get("checked_at", 0))
        if time.time() - checked_at > NODE_HEALTH_MAX_AGE:
            return set()
        return {host for host, ok in payload.get("nodes", {}).items() if not ok}
    except Exception:
        return set()


def filter_alive(links: list[str]) -> list[str]:
    if not HEALTH_ENABLED:
        return links
    with _health_lock:
        snapshot = dict(_probe_fails)
    dead = {target for target, fails in snapshot.items() if fails >= HEALTH_FAILS}
    probed_dead = _probed_dead_hosts()
    if not dead and not probed_dead:
        return links

    host_targets: dict[str, set[tuple[str, int]]] = {}
    for host, port in snapshot:
        host_targets.setdefault(host, set()).add((host, port))
    dead_hosts = {host for host, targets in host_targets.items() if targets <= dead}
    dead_hosts |= probed_dead

    kept: list[str] = []
    for uri in links:
        endpoint = _uri_endpoint(uri)
        if endpoint is None:
            kept.append(uri)
        elif endpoint[0] in dead_hosts:
            continue  # host-level verdict covers every protocol on it
        elif _is_udp_uri(uri):
            kept.append(uri)
        elif endpoint not in dead:
            kept.append(uri)
    return kept or links


def _probe_endpoint(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=HEALTH_TIMEOUT):
            return True
    except OSError:
        return False


def _health_loop() -> None:
    while True:
        with _health_lock:
            targets = list(_probe_fails.keys())
        for host, port in targets:
            alive = _probe_endpoint(host, port)
            with _health_lock:
                if (host, port) in _probe_fails:
                    _probe_fails[(host, port)] = 0 if alive else _probe_fails[(host, port)] + 1
        time.sleep(HEALTH_INTERVAL)


# Happ app-management headers on the /sub/<token>/auto flavor. The body itself
# carries the «⚡️ Авто-обход» balancer as the first entry (see build_auto_json),
# so here we only make Happ reconnect on launch to the last-used entry (the
# balancer, after the first tap) and refresh hourly so pruned dead nodes and a
# re-picked balancer target propagate fast. Non-Happ clients ignore these.
AUTO_HEADERS = {
    "profile-update-interval": "1",
    "subscription-autoconnect": "1",
    "subscription-autoconnect-type": "lastused",
    "subscription-ping-onopen-enabled": "1",
}


# Proxy URIs Marzban issues share the `scheme://creds@host:port?...#remark`
# shape (vless, trojan, ss, …), so the host extraction is protocol-agnostic.
def _uri_host(uri: str) -> str | None:
    try:
        after_at = uri.split("@", 1)[1]
    except IndexError:
        return None
    return after_at.split(":", 1)[0].split("?", 1)[0].split("/", 1)[0] or None


def _hy2_uri(node: dict) -> str:
    remark = urllib.parse.quote(f"{node['flag']} {node['name']} · Hysteria2")
    host, port = node["hy2_host"], node["hy2_port"]
    return (
        f"hysteria2://{node['hy2_pass']}@{host}:{port}"
        f"?sni={host}&insecure=0#{remark}"
    )


def _trojan_uri(node: dict) -> str:
    # Standalone per-node Trojan-TLS (not a Marzban inbound), hand-added like Hy2.
    remark = urllib.parse.quote(f"{node['flag']} {node['name']} · Trojan")
    host, port = node["hy2_host"], node["trojan_port"]
    return (
        f"trojan://{node['trojan_pass']}@{host}:{port}"
        f"?security=tls&sni={host}&type=tcp#{remark}"
    )


def _http_get_sub(url: str) -> tuple[str, str | None] | None:
    """Fetch a base64 (or raw) subscription body. Returns (decoded_uris_text,
    userinfo_header), or None on any transport error / empty body."""
    req = urllib.request.Request(url, headers={"User-Agent": "v2rayNG/1.8.5"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
            raw = resp.read().decode("utf-8", "replace").strip()
            userinfo = resp.headers.get("subscription-userinfo")
    except Exception:
        return None
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw + "===").decode("utf-8", "replace")
    except Exception:
        decoded = raw
    return decoded, userinfo


def _fetch_upstream_sub(token: str) -> tuple[str, str | None] | None:
    """Fetch one per-user subscription from Marzban."""
    return _http_get_sub(f"{MARZBAN_BASE}/sub/{token}")


def _userinfo_expired(userinfo: str | None) -> bool:
    """True when subscription-userinfo carries a past expire timestamp
    (expire=0 or absent means unlimited and is never treated as expired)."""
    if not userinfo:
        return False
    match = re.search(r"expire=(\d+)", userinfo)
    if not match:
        return False
    expire = int(match.group(1))
    return 0 < expire < time.time()


# A far-future stand-in for "never expires".
#
# The convention is that expire=0 means unlimited, and this gateway reads it
# that way (see _userinfo_expired). Clients do not all agree: an unlimited link
# was reported as «link has expired» when a device tried to add it on
# 2026-08-24, while the gateway had served that exact token sixteen entries,
# four times in five minutes, with no error. Zero is also a perfectly good
# timestamp pointing at 1970, and a client that reads it as one sees a
# subscription that ran out fifty years ago.
#
# Only unlimited accounts carry expire=0, which is why nothing else showed this.
# Sending a real date instead removes the ambiguity without changing what the
# subscription is worth.
_NEVER_EXPIRES = 4102444800  # 2100-01-01 UTC


def _normalise_userinfo(userinfo: str | None) -> str | None:
    """Replace an unlimited expire=0 with a date no client can misread."""
    if not userinfo:
        return userinfo
    return re.sub(r"expire=0(?![0-9])", f"expire={_NEVER_EXPIRES}", userinfo)


def _marzban_sub_active(token: str) -> bool:
    """False when Marzban reports the user as expired/disabled/limited.

    Marzban keeps serving proxy links for such users even though xray already
    rejects them, and the gateway's hand-added Hysteria2/Trojan extras use
    node-wide shared secrets that outlive the panel expiry — so the gateway
    must blank the whole subscription itself. Fails open: a panel hiccup must
    never wipe a paying user's client config.
    """
    req = urllib.request.Request(
        f"{MARZBAN_BASE}/sub/{token}/info", headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL) as resp:
            info = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return True
    return str(info.get("status", "active")).lower() in ("", "active", "on_hold")


# Marzban auto-names a link it generates for a node with no curated host as
# `<node> (<user>) [PROTOCOL - transport]`. Those duplicate a location we
# already publish under a proper name, carry the wrong node's keys, and simply
# fail when tapped — adding the USA node produced eight of them at once. Every
# remark we curate is a country name, so the template is safe to recognise.
_MARZBAN_DEFAULT_REMARK = re.compile(r"\[[A-Za-z0-9]+ - [a-z0-9]+\]\s*$")


def _is_default_named(uri: str) -> bool:
    remark = urllib.parse.unquote(uri.partition("#")[2])
    return bool(_MARZBAN_DEFAULT_REMARK.search(remark))


def combine_links(decoded: str) -> list[str]:
    """Pass through every proxy link Marzban issued and append each node's
    Hysteria2 endpoint once (after the node's first link), preserving order.

    Protocol-agnostic: vless, trojan, shadowsocks etc. from Marzban all flow
    through, so a new panel inbound needs no gateway change. Each node's
    standalone extras (Hysteria2, Trojan) are hand-appended once after the
    node's first link, so a location exposing both VLESS and a panel Trojan
    doesn't list its Hy2/Trojan twice.
    """
    proxy_uris = [
        line.strip()
        for line in decoded.splitlines()
        if "://" in line.strip() and not _is_default_named(line.strip())
    ]
    combined: list[str] = []
    extras_done: set[str] = set()
    for uri in proxy_uris:
        combined.append(uri)
        host = _uri_host(uri)
        node = NODES.get(host) if host else None
        if node and host not in extras_done:
            extras_done.add(host)
            if node.get("hy2_pass"):
                combined.append(_hy2_uri(node))
            if node.get("trojan_pass"):
                combined.append(_trojan_uri(node))
    return combined


def _log_served(token: str, user_agent: str, flavor: str, body: str) -> None:
    """One line per subscription handed out: who asked, and what they got.

    Twice now a question about what a user is actually seeing — «where did
    «Авто-обход» go», «why are these duplicated» — could not be answered because
    nothing records it. The client string is the deciding fact: it is what
    selects the JSON body over the plain list, and a client we fail to
    recognise silently receives a subscription with no automatic entry at all.

    The token identifies a paying account, so only its head is written; enough
    to correlate two requests, not enough to replay one.
    """
    try:
        if flavor == "json":
            count = len(json.loads(body))
        else:
            count = len([l for l in base64.b64decode(body + "===").decode(
                "utf-8", "replace").splitlines() if "://" in l])
    except Exception:  # noqa: BLE001
        count = -1
    print(
        f"served token={token[:8]}… flavor={flavor} entries={count} "
        f"client={(user_agent or '(none)')[:60]!r}",
        flush=True,
    )


def _cascade_link(port: int, remark: str) -> str:
    """One standalone 🇷🇺→<country> cascade entry: VLESS Reality to the Moscow
    relay's per-country inbound (its keypair, VLESS/TCP only). The relay does the
    RU-vs-foreign split routing server-side and forwards this port's foreign
    traffic to the matching exit, so the client needs nothing but this link."""
    return (
        f"vless://{CASCADE_UUID}@{RU_RELAY_HOST}:{port}"
        f"?security=reality&type=tcp&flow=xtls-rprx-vision&sni={RU_RELAY_HOST}"
        f"&fp=firefox&pbk={CASCADE_PBK}&sid={CASCADE_SID}"
        f"#{urllib.parse.quote(remark)}"
    )


def build_cascade_links(links: list[str]) -> list[str]:
    """Hand-add a 🇷🇺→<country> cascade entry per exit for an active subscription.

    Emitted only when enabled and the user already has at least one live link
    (resolve_links has already blanked expired subs), so a lapsed account never
    receives the shared-secret cascade here. All entries share the relay host, so
    reorder_by_proximity groups them first, in CASCADE_COUNTRIES order.

    A cascade whose exit is down is left out. Health is tracked per host, and
    every cascade lives on the relay — so when Frankfurt went dark on
    2026-08-06 its direct entries were pruned correctly while «🇩🇪 Германия ✅
    РУ сервисы» stayed, first in the list and first in «Авто-обход», pointing
    at a machine that was switched off. The relay being up says nothing about
    where it forwards to."""
    if not CASCADE_ENABLED or not links:
        return []
    dead = _probed_dead_hosts()
    return [
        _cascade_link(port, remark)
        for port, remark, exit_host in CASCADE_COUNTRIES
        if exit_host not in dead
    ]


# --- учёт устройств -------------------------------------------------------------
# Тариф обещает «до 3 устройств», но до сих пор это была только надпись: ссылку
# можно было раздать кому угодно, и один оплаченный доступ работал на десятке
# телефонов. Приложения сами присылают идентификатор устройства (`x-hwid`, а с ним
# модель и систему) — по нему лимит соблюдается прямо на выдаче.
#
# Правила, которые важнее самого лимита:
#   • приложение, которое идентификатор не шлёт, не блокируется никогда — таких
#     около десятой части обращений, и оставить их без серверов хуже, чем
#     недосчитаться устройства;
#   • устройство, которым не пользовались DEVICE_IDLE_DAYS, освобождает место —
#     человек сменил телефон, и слот не должен держаться за старым вечно;
#   • любая ошибка хранилища трактуется в пользу пользователя (выдаём серверы);
#   • отказ — это не пустой список (приложение показывает его как поломку
#     подписки), а одна понятная запись с адресом поддержки.
#
# DEVICE_LIMIT=0 выключает всё. DEVICE_ENFORCE=0 — режим наблюдения: устройства
# считаются и видны в отчёте, но никого не отключают. Так лимит включается по
# фактам, а не на ощупь: сначала неделя наблюдения, потом решение о цифре.
DEVICE_LIMIT = int(os.environ.get("DEVICE_LIMIT", "0") or 0)
DEVICE_ENFORCE = os.environ.get("DEVICE_ENFORCE", "1").lower() not in ("0", "false", "no", "")
DEVICE_DB = os.environ.get("DEVICE_DB", "/var/lib/unlock-subgw/devices.sqlite3")
DEVICE_IDLE_DAYS = int(os.environ.get("DEVICE_IDLE_DAYS", "14") or 14)
# Цифра лимита у тарифов разная: пробник — два устройства (телефон и компьютер,
# иначе человек упрётся в лимит ровно на знакомстве с сервисом), платные — три.
# Панель этого не знает: в ответе `/sub/<token>/info` лимита устройств нет. Знает
# бот, и его API живёт на этой же машине, поэтому шлюз спрашивает лимит у него.
# Ответ живёт в памяти DEVICE_LIMIT_TTL секунд: подписка меняется редко, а
# ходить в соседнюю службу на каждое обновление подписки незачем.
DEVICE_LIMIT_API = os.environ.get("DEVICE_LIMIT_API", "")
DEVICE_LIMIT_API_TOKEN = os.environ.get("DEVICE_LIMIT_API_TOKEN", "")
DEVICE_LIMIT_TTL = int(os.environ.get("DEVICE_LIMIT_TTL", "600") or 600)
# Неудачу помним недолго: если бот перезапускается, лимиты должны вернуться
# сами, а не через десять минут.
DEVICE_LIMIT_FAIL_TTL = 60
_PLAN_LIMITS: dict[str, tuple[float, int]] = {}


def _names(raw: str) -> frozenset[str]:
    """Панельные имена из настройки: «tg_1, tg_2» → {"tg_1", "tg_2"}."""

    return frozenset(part.strip() for part in raw.split(",") if part.strip())


# Люди, которым владелец снял лимит устройств вручную. Цифру лимита называет
# тариф, и правкой в базе её не перебить — нужен явный список, который видно
# в настройках шлюза и который так же легко убрать.
DEVICE_LIMIT_EXEMPT = _names(os.environ.get("DEVICE_LIMIT_EXEMPT", ""))

# Корпоративные подписки (18.09.2026, заказ на финские серверы). Marzban сам
# включает новый вход всем пользователям, поэтому граница проходит здесь:
# серверы из CORP_HOSTS видят только учётные записи из CORP_USERS — и видят
# только их. Каскад, вход для белых списков и Hy2/Trojan с общим ключом им не
# выдаются: у заказа свои серверы и своё число устройств.
CORP_HOSTS = _names(os.environ.get("CORP_HOSTS", ""))
CORP_USERS = _names(os.environ.get("CORP_USERS", ""))
CORP_DEVICE_LIMIT = int(os.environ.get("CORP_DEVICE_LIMIT", "3") or 3)


def _logins(raw: str) -> dict[str, str]:
    """Логины из настройки: «corp_fi_1:пароль, corp_fi_2:пароль» → {имя: пароль}."""

    pairs = (part.strip().partition(":") for part in raw.split(","))
    return {name: secret for name, sep, secret in pairs if name and sep and secret}


# Hysteria2 на корпоративных серверах — у каждой учётной записи свой логин
# (userpass на сервере), а не общий пароль, как на польском узле: общий не
# отозвать у одного клиента, когда закончится его срок.
CORP_HY2 = _logins(os.environ.get("CORP_HY2", ""))
CORP_HY2_PORT = int(os.environ.get("CORP_HY2_PORT", "443") or 443)


def corp_filter(links: list[str], *, corporate: bool) -> list[str]:
    """Корпоративной ссылке — только её серверы, всем остальным — всё, кроме них."""

    if not CORP_HOSTS:
        return links
    return [link for link in links if (_uri_host(link) in CORP_HOSTS) == corporate]


def build_corp_hy2_links(username: str | None, links: list[str]) -> list[str]:
    """Hysteria2 на каждый корпоративный сервер из подписки — со своим логином."""

    secret = CORP_HY2.get(username or "")
    if not secret:
        return []
    extras: list[str] = []
    seen: set[str] = set()
    for link in links:
        host = _uri_host(link)
        if host not in CORP_HOSTS or host in seen:
            continue
        seen.add(host)
        # «🇫🇮 Финляндия 1 · XHTTP» → «🇫🇮 Финляндия 1 · Hysteria2»
        name = urllib.parse.unquote(link.partition("#")[2]).split(" · ", 1)[0] or host
        extras.append(
            f"hysteria2://{username}:{secret}@{host}:{CORP_HY2_PORT}"
            f"?sni={host}&insecure=0#{urllib.parse.quote(f'{name} · Hysteria2')}"
        )
    return extras


DEVICE_LIMIT_REMARK = "❗️ Лимит устройств — напишите в поддержку"
DEVICE_LIMIT_ANNOUNCE = (
    "❗️ Достигнут лимит устройств по подписке.\n"
    "Отключите лишнее устройство или напишите в поддержку."
)
_DEVICE_LOCK = threading.Lock()


@functools.lru_cache(maxsize=1)
def _device_store() -> sqlite3.Connection | None:
    """Хранилище устройств, или None — тогда лимит просто не действует."""

    try:
        directory = os.path.dirname(DEVICE_DB)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = sqlite3.connect(DEVICE_DB, check_same_thread=False)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS devices ("
            " username TEXT NOT NULL, hwid TEXT NOT NULL, model TEXT, os TEXT,"
            " first_seen REAL NOT NULL, last_seen REAL NOT NULL,"
            " PRIMARY KEY (username, hwid))"
        )
        conn.commit()
        return conn
    except Exception as exc:  # noqa: BLE001 — без хранилища выдача продолжается
        print(f"devices: хранилище недоступно ({type(exc).__name__}), лимит не действует", flush=True)
        return None


def plan_device_limit(username: str) -> int:
    """Сколько устройств обещает тариф этой подписки. 0 — не ограничивать.

    Без настроенного API (и при любой его ошибке) действует общая цифра
    DEVICE_LIMIT: недоступность соседней службы не повод отключать человеку
    устройство, которое он оплатил.
    """

    if username in CORP_USERS:
        return CORP_DEVICE_LIMIT
    if not DEVICE_LIMIT_API:
        return DEVICE_LIMIT
    cached = _PLAN_LIMITS.get(username)
    if cached is not None and cached[0] > time.time():
        return cached[1]

    limit = DEVICE_LIMIT
    ttl = DEVICE_LIMIT_FAIL_TTL
    try:
        telegram_id = username.removeprefix("tg_")
        req = urllib.request.Request(
            DEVICE_LIMIT_API.format(telegram_id=urllib.parse.quote(telegram_id)),
            headers={"Authorization": f"Bearer {DEVICE_LIMIT_API_TOKEN}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        subscription = payload.get("subscription") or {}
        stated = subscription.get("deviceLimit")
        # null у тарифа означает «без ограничения», а не «ограничить общей цифрой».
        limit = int(stated) if isinstance(stated, int) else 0
        ttl = DEVICE_LIMIT_TTL
    except Exception as exc:  # noqa: BLE001 — см. docstring: ошибка не отключает устройства
        print(f"devices: лимит тарифа не узнать ({type(exc).__name__}), беру общий", flush=True)
    _PLAN_LIMITS[username] = (time.time() + ttl, limit)
    return limit


def device_allowed(
    username: str | None, hwid: str | None, *, model: str | None = None, os_name: str | None = None
) -> bool:
    """Запомнить устройство и сказать, помещается ли оно в лимит подписки."""

    if DEVICE_LIMIT <= 0 or not username or not hwid:
        return True
    if username in DEVICE_LIMIT_EXEMPT:
        return True
    conn = _device_store()
    if conn is None:
        return True
    limit = plan_device_limit(username)
    if limit <= 0:
        return True
    now = time.time()
    try:
        with _DEVICE_LOCK:
            conn.execute("DELETE FROM devices WHERE last_seen < ?", (now - DEVICE_IDLE_DAYS * 86400,))
            known = conn.execute(
                "SELECT 1 FROM devices WHERE username = ? AND hwid = ?", (username, hwid)
            ).fetchone()
            if known is None:
                used = conn.execute(
                    "SELECT COUNT(*) FROM devices WHERE username = ?", (username,)
                ).fetchone()[0]
                if used >= limit:
                    mode = "отказ" if DEVICE_ENFORCE else "наблюдение"
                    print(
                        f"device limit hit ({mode}) username={username} devices={used}/{limit}"
                        f" hwid={hwid[:12]}",
                        flush=True,
                    )
                    if DEVICE_ENFORCE:
                        conn.commit()
                        return False
                conn.execute(
                    "INSERT INTO devices (username, hwid, model, os, first_seen, last_seen)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (username, hwid, model, os_name, now, now),
                )
            else:
                conn.execute(
                    "UPDATE devices SET last_seen = ?, model = COALESCE(?, model),"
                    " os = COALESCE(?, os) WHERE username = ? AND hwid = ?",
                    (now, model, os_name, username, hwid),
                )
            conn.commit()
    except Exception as exc:  # noqa: BLE001 — учёт не повод оставить человека без серверов
        print(f"devices: ошибка учёта ({type(exc).__name__}), пропускаю", flush=True)
        return True
    return True


def devices_of(username: str) -> list[dict]:
    """Устройства подписки — для поддержки и экрана «Устройства» в боте."""

    conn = _device_store()
    if conn is None:
        return []
    rows = conn.execute(
        "SELECT hwid, model, os, first_seen, last_seen FROM devices"
        " WHERE username = ? ORDER BY first_seen",
        (username,),
    ).fetchall()
    return [
        {"hwid": row[0], "model": row[1], "os": row[2], "first_seen": row[3], "last_seen": row[4]}
        for row in rows
    ]


def forget_devices(username: str, hwid: str | None = None) -> int:
    """Сбросить привязку — человек сменил телефон или раздал ссылку и просит помочь."""

    conn = _device_store()
    if conn is None:
        return 0
    with _DEVICE_LOCK:
        if hwid:
            cur = conn.execute(
                "DELETE FROM devices WHERE username = ? AND hwid = ?", (username, hwid)
            )
        else:
            cur = conn.execute("DELETE FROM devices WHERE username = ?", (username,))
        conn.commit()
    return cur.rowcount or 0


def device_gate(token: str, headers) -> str | None:
    """Тело-заглушка, если устройство не помещается в лимит подписки, иначе None.

    Отдельной функцией, чтобы решение можно было проверить тестом, не поднимая
    HTTP-сервер: именно здесь решается, увидит человек серверы или объяснение.
    """

    if DEVICE_LIMIT <= 0:
        return None
    hwid = (headers.get("x-hwid") or "").strip()
    username = _token_username(token)
    if not hwid or username is None:
        return None
    if device_allowed(
        username, hwid, model=headers.get("x-device-model"), os_name=headers.get("x-device-os")
    ):
        return None
    return device_limit_body()


def device_limit_body() -> str:
    """Ответ устройству сверх лимита: одна запись вместо пустоты."""

    link = (
        "vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1"
        "?security=none&type=tcp&encryption=none#" + urllib.parse.quote(DEVICE_LIMIT_REMARK)
    )
    return base64.b64encode(link.encode("utf-8")).decode("ascii")


# --- 📶 мобильный интернет в «белых списках» -------------------------------------
# Российские операторы периодически опускают мобильный интернет до белого списка:
# открыты только разрешённые службы, а все зарубежные адреса недоступны. Туннель
# переживает это лишь при двух условиях сразу — первый узел стоит на российском
# адресе, и рукопожатие называет службу из списка.
#
# Отсюда устройство записи: VLESS Reality на входе в российском облаке, а в SNI —
# имя разрешённого сервиса (по умолчанию `max.ru`, национальный мессенджер).
# Reality на том сервере направляет неопознанные соединения на настоящий max.ru,
# поэтому проверяющий видит его собственный сертификат. Российские адреса вход
# отдаёт со своего же адреса, остальное передаёт на наши зарубежные узлы.
#
# Запись спит, пока не куплен сервер: без MOBILE_HOST/UUID ничего не выдаётся.
# Она намеренно не попадает в «Авто-обход» (см. build_auto_json): трафик в
# российском облаке платный, а канал этот — аварийный, а не для всех подряд.
MOBILE_HOST = os.environ.get("MOBILE_HOST", "")
MOBILE_PORT = int(os.environ.get("MOBILE_PORT", "443") or 443)
# Имя, которое видит оператор. Своим адресом маскироваться бессмысленно: в белом
# списке его нет, а значит и соединения не будет.
MOBILE_SNI = os.environ.get("MOBILE_SNI", "max.ru")
MOBILE_UUID = os.environ.get("MOBILE_UUID", "")
MOBILE_PBK = os.environ.get("MOBILE_PBK", "")
MOBILE_SID = os.environ.get("MOBILE_SID", "")
MOBILE_REMARK = os.environ.get("MOBILE_REMARK", "📶 Мобильный интернет")


def _mobile_link() -> str | None:
    """Ссылка на российский вход, или None, пока он не настроен."""

    if not (MOBILE_HOST and MOBILE_UUID and MOBILE_PBK):
        return None
    return (
        f"vless://{MOBILE_UUID}@{MOBILE_HOST}:{MOBILE_PORT}"
        f"?security=reality&type=tcp&flow=xtls-rprx-vision&sni={MOBILE_SNI}"
        f"&fp=firefox&pbk={MOBILE_PBK}&sid={MOBILE_SID}"
        f"#{urllib.parse.quote(MOBILE_REMARK)}"
    )


def build_mobile_links(links: list[str]) -> list[str]:
    """Добавить запись для белых списков живой подписке.

    Как и каскад, это ссылка с общим секретом, поэтому она выдаётся только
    тому, у кого уже есть хотя бы один живой сервер: resolve_links к этому
    моменту уже обнулил подписку истёкшему пользователю.
    """
    link = _mobile_link()
    if link is None or not links:
        return []
    return [link]


# RU-audience proximity order: the app's default/top server should be the
# lowest-ping one. The 🇷🇺→🇩🇪 cascade enters on a domestic Moscow IP (the
# un-throttled first hop) so it wins outright; Germany/Poland/Netherlands are
# ~30-70ms direct; the US is ~250ms, so it goes last (kept available, just not
# the default a user taps into).
NODE_PRIORITY = {
    # Лидирует не по замеру, а по решению владельца: это витрина, её показывают
    # в рекламе, и она должна быть первой локацией, которую человек видит после
    # двух автоматических режимов. По скорости она вровень с Франкфуртом —
    # 151 мс против 141 и 44.9 Мбит/с против 43.7, замер из Москвы 2026-08-31,
    # так что первое место ей ничего не стоит.
    "2.59.162.34.sslip.io": -1,     # 🇱🇹 Литва
    RU_RELAY_HOST: 0,               # 🇷🇺→🇩🇪 каскад — первый, только когда включён
    "78.17.154.225.sslip.io": 1,    # 🇵🇱 Польша (Варшава — ближе всего европ. части РФ)
    "166.0.28.132.sslip.io": 2,     # 🇩🇪 Германия (Франкфурт)
    "107.189.22.160.sslip.io": 3,   # 🇳🇱 Нидерланды
    "172.86.119.133.sslip.io": 4,   # 🇺🇸 США (дальше всего)
}
_DEFAULT_PRIORITY = 2  # unknown hosts sit mid-list, ahead of the far NL/US nodes


def reorder_by_proximity(links: list[str]) -> list[str]:
    """Order locations closest-to-RU first (Польша → Нидерланды → … → США).

    Stable within a location: each node's VLESS/Hy2/Trojan stay grouped and in
    their original order (same host → same priority → tie broken by index)."""
    indexed = list(enumerate(links))
    indexed.sort(key=lambda pair: (NODE_PRIORITY.get(_uri_host(pair[1]) or "", _DEFAULT_PRIORITY), pair[0]))
    return [uri for _, uri in indexed]


def resolve_links(token: str) -> tuple[list[str], str | None] | None:
    """Resolve a token to its live proxy links (health-filtered).

    Returns (links, userinfo): links is empty when the subscription is
    expired/blank/disabled. Returns None only when the token is unknown (404).
    Shared by the base64 and the JSON («Авто-обход») subscription flavors.
    """
    fetched = _fetch_upstream_sub(token)
    if fetched is None:
        return None
    decoded, userinfo = fetched
    if _userinfo_expired(userinfo) or not _marzban_sub_active(token):
        return [], userinfo
    username = _token_username(token)
    corporate = username in CORP_USERS
    combined = corp_filter(combine_links(decoded), corporate=corporate)
    if not combined:
        return [], userinfo
    if corporate:
        combined = combined + build_corp_hy2_links(username, combined)
    else:
        combined = combined + build_cascade_links(combined) + build_mobile_links(combined)
    _register_probe_targets(combined)
    return reorder_by_proximity(filter_alive(combined)), userinfo


def build_combined(token: str) -> tuple[str, str | None] | None:
    resolved = resolve_links(token)
    if resolved is None:
        return None
    links, userinfo = resolved
    payload = base64.b64encode("\n".join(links).encode("utf-8")).decode("ascii")
    return payload, userinfo


def build_auto_json(token: str) -> tuple[str, str | None, bool] | None:
    """Build the «Авто-обход» body for the /auto flavor.

    The body carries both automatic entries — «Авто-обход» and
    «Автопереключение» — so the /split link is now just an alias of the ordinary
    one, kept working for anyone who already imported it.

    Returns (body, userinfo, is_json): a JSON array of xray configs (balancer
    first) when at least one xray-core server exists, else the plain base64
    body (is_json False) so nothing regresses. None on an unknown token.
    """
    resolved = resolve_links(token)
    if resolved is None:
        return None
    links, userinfo = resolved
    configs = build_json_subscription(
        links, exclude_from_balancer={MOBILE_HOST} if MOBILE_HOST else frozenset()
    )
    if configs:
        # Compact separators, because the size of this body decides whether a
        # Russian client can fetch it at all. The path from RU to the gateway is
        # throttled by volume: measured from Moscow on 2026-08-11, the same
        # subscription took 0.78s compressed (2.7 KB) and timed out after 40s
        # uncompressed (20 KB of 67 transferred). A client that does not
        # negotiate compression gets no subscription, so the raw body has to be
        # small on its own. Default separators spend a space after every comma
        # and colon across thirteen configs.
        return json.dumps(configs, ensure_ascii=False, separators=(",", ":")), userinfo, True
    payload = base64.b64encode("\n".join(links).encode("utf-8")).decode("ascii")
    return payload, userinfo, False


def happ_redirect_page(sub_url: str) -> str:
    """HTML that bounces the browser into Happ's `happ://add/<sub_url>` deep link.

    Telegram rejects custom URL schemes in inline buttons, so the bot button is a
    plain HTTPS link to `/happ/<token>` which serves this page; the page then
    hands off to the app (JS + meta-refresh) with a tappable fallback.
    """
    happ_url = f"happ://add/{sub_url}"
    href = html.escape(happ_url, quote=True)
    js_url = json.dumps(happ_url)
    return (
        "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>UnLock VPN</title>"
        f"<script>location.replace({js_url})</script>"
        f"<meta http-equiv=\"refresh\" content=\"0;url={href}\"></head>"
        "<body style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
        "text-align:center;padding:48px 20px;color:#1a1a1a\">"
        "<h2>Открываю Happ…</h2>"
        "<p>Если приложение не открылось автоматически:</p>"
        f"<p><a href=\"{href}\" style=\"display:inline-block;padding:13px 24px;"
        "background:#111;color:#fff;border-radius:12px;text-decoration:none;"
        "font-weight:600\">Открыть в Happ</a></p>"
        "<p style=\"color:#888;font-size:14px;margin-top:28px\">Нет приложения? "
        "Установите Happ из App Store или Google Play и нажмите кнопку снова.</p>"
        "</body></html>"
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "unlock-subgw"
    # A stalled client must die in its own handler thread, not hold a socket
    # open forever.
    timeout = 30

    def log_message(self, *args):  # silence default logging
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/health", "/healthz"):
            self._send(200, b"ok", "text/plain")
            return
        happ_prefix = "/happ/"
        if path.startswith(happ_prefix):
            token, _, tail = path[len(happ_prefix):].partition("/")
            if not _TOKEN_RE.match(token):
                self._send(404, b"not found", "text/plain")
                return
            base = PUBLIC_BASE or f"https://{self.headers.get('Host', '')}".rstrip("/")
            sub_url = f"{base}/sub/{token}"
            if tail.rstrip("/") == "auto":
                sub_url += "/auto"
            page = happ_redirect_page(sub_url)
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        prefix = "/sub/"
        if not path.startswith(prefix):
            self._send(404, b"not found", "text/plain")
            return
        token, _, tail = path[len(prefix):].partition("/")
        flavor = tail.rstrip("/")
        is_auto = flavor == "auto"
        # Hysteria2 runs on a core of its own and cannot appear inside an
        # xray-JSON body, so a Happ user served JSON never sees it. This flavor
        # forces the base64 list for any client, which is the only way to hand
        # Happ the Hy2 entries — offered alongside the ordinary link rather than
        # replacing it, so «Авто-обход» is not sacrificed to get Hysteria.
        force_plain = flavor == "hy2"
        # Volunteer build of the split: Russian banks and government services on
        # foreign TLDs leave the tunnel too. Handed out by link only, so it is
        # opt-in and comparable against the ordinary subscription.
        is_split = flavor == "split"
        if not token:
            self._send(404, b"not found", "text/plain")
            return
        # A browser gets the connect landing; VPN clients get the raw config.
        if _TOKEN_RE.match(token) and _is_browser(self.headers.get("User-Agent", "")):
            base = PUBLIC_BASE or f"https://{self.headers.get('Host', '')}".rstrip("/")
            # Stay on this host. Sending the browser to the marketing site made
            # a pasted subscription link only as reachable as that site: while
            # the old domain was filtered a user got a plain timeout, and once
            # it moved, Vercel answered our origin with a bot challenge. The
            # /happ/ page lives here, needs nothing else up, and is reachable
            # wherever the subscription link itself is.
            location = f"{base}/happ/{token}/{flavor}" if flavor else f"{base}/happ/{token}"
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        # «⚡️ Авто-обход» rides inside the ordinary subscription for clients that
        # can parse xray-JSON, so a user who imports the one link already has it
        # as the first server — no second link to hand out. Historically this was
        # /auto-only because the base64 body was needed to carry Hysteria2, which
        # xray-JSON cannot express. Hy2 is back, so the JSON body does lose it —
        # that is what the /hy2 flavor above exists to hand over. Other clients
        # keep the base64 URI list, Hysteria2 included.
        ua = self.headers.get("User-Agent", "")
        blocked = device_gate(token, self.headers)
        if blocked is not None:
            _log_served(token, ua, "device-limit", blocked)
            self._send(
                200,
                blocked.encode("ascii"),
                "text/plain; charset=utf-8",
                {
                    "profile-title": PROFILE_TITLE_HEADER,
                    "announce": "base64:"
                    + base64.b64encode(DEVICE_LIMIT_ANNOUNCE.encode("utf-8")).decode("ascii"),
                },
            )
            return
        wants_json = not force_plain and (
            is_auto or is_split or (AUTO_IN_SUB and _supports_xray_json(ua))
        )
        if wants_json:
            auto = build_auto_json(token)
            if auto is None:
                self._send(404, b"invalid subscription", "text/plain")
                return
            body, userinfo, is_json = auto
            extra = _client_headers(token, flavor)
            # Autoconnect/1h-refresh headers stay exclusive to the explicit /auto
            # link: the plain subscription must not start dialling on its own.
            if is_json and (is_auto or is_split):
                extra.update(AUTO_HEADERS)
            if userinfo:
                extra["subscription-userinfo"] = _normalise_userinfo(userinfo)
            ctype = "application/json; charset=utf-8" if is_json else "text/plain; charset=utf-8"
            _log_served(token, ua, "json" if is_json else "base64", body)
            self._send(200, body.encode("utf-8"), ctype, extra)
            return

        result = build_combined(token)
        if result is None:
            self._send(404, b"invalid subscription", "text/plain")
            return
        payload, userinfo = result
        extra = _client_headers(token, flavor)
        if userinfo:
            extra["subscription-userinfo"] = _normalise_userinfo(userinfo)
        _log_served(token, ua, "base64", payload)
        self._send(200, payload.encode("ascii"), "text/plain; charset=utf-8", extra)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if not any(key.lower() == "profile-update-interval" for key in (extra or {})):
            # Hours between client refreshes. This is also how long a fix takes
            # to reach someone who never reopens the app, and how long a node
            # pulled by the health prober stays in their list — 12h meant a
            # routing correction landed the next day.
            #
            # Cut from six to two on 2026-08-10: a routing fix went out at 13:42
            # and the machine it was written for was still running the config it
            # had fetched at 13:11 half an hour later, so the report came back
            # "no change" for a fix that had simply not arrived. Two hours keeps
            # the fetch cheap — the body is a few tens of KB — while making a
            # correction land inside the session it was made in.
            self.send_header("Profile-Update-Interval", "2")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    if HEALTH_ENABLED:
        threading.Thread(target=_health_loop, daemon=True, name="node-health").start()
    server = ThreadingHTTPServer((BIND_HOST, LISTEN_PORT), Handler)
    scheme = "http"
    if CERT_FILE and KEY_FILE:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
        # Handshake must happen in the per-request handler thread; with
        # do_handshake_on_connect=True one stalled client blocks accept() and
        # takes the whole gateway down (observed 2026-07-10).
        server.socket = ctx.wrap_socket(
            server.socket, server_side=True, do_handshake_on_connect=False
        )
        scheme = "https"
    print(f"sub-gateway on {scheme}://{BIND_HOST}:{LISTEN_PORT}, marzban={MARZBAN_BASE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
