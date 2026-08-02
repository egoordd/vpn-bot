#!/usr/bin/env python3
"""End-to-end node health prober.

The gateway's built-in check only opens a TCP socket, so a node that accepts
connections and then silently drops traffic looks perfectly healthy — that is
exactly how the Amsterdam node behaved on 2026-07-28, staying in every
subscription while users sat on "connected but nothing loads". A tunnel is only
healthy if bytes actually come back through it, so this probes the real thing:
it dials each node with xray and fetches a 204 over the tunnel.

Verdicts land in a small JSON file the gateway reads. Nodes that fail are
dropped from served subscriptions, so a silently-broken exit never reaches a
user and never poisons the «Авто-обход» balancer.

Runs on the bot VPS from a systemd timer. Stdlib only, like the gateway.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

XRAY_BIN = os.environ.get("XRAY_BIN", "/usr/local/bin/xray")
# Subscription of the service account that carries every exit inbound, so one
# fetch yields a link per node without hardcoding credentials here.
PROBE_SUB_URL = os.environ.get("PROBE_SUB_URL", "")
# Endpoints that exist outside the panel and would otherwise go unwatched. The
# Moscow cascade relay is the case that matters: it is not a Marzban node, yet
# all four 🇷🇺→<country> entries — the first things in every subscription —
# terminate on it. Unprobed, it could black-hole the top of everyone's list
# indefinitely and nothing would notice. Newline- or comma-separated links.
PROBE_EXTRA_LINKS = os.environ.get("PROBE_EXTRA_LINKS", "")
# Where the probe is executed from. Empty runs it locally; set to a host we can
# reach over SSH to measure from that vantage instead. Reachability is not a
# property of a node alone — it is a property of the path — so this must be a
# machine on the same side of the censorship as the customers.
PROBE_FROM_HOST = os.environ.get("PROBE_FROM_HOST", "")
PROBE_FROM_XRAY = os.environ.get("PROBE_FROM_XRAY", "/usr/local/bin/xray")
HEALTH_FILE = os.environ.get("NODE_HEALTH_FILE", "/run/unlock-node-health.json")
# A 204 generator: no body, no TLS handshake to a third party inside the tunnel.
PROBE_URL = os.environ.get("PROBE_TARGET", "http://cp.cloudflare.com/generate_204")
PROBE_TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "12"))
# Two tries before calling a node dead: a single timeout on a busy exit is
# normal, and dropping a working node hurts more than keeping a flaky one.
PROBE_ATTEMPTS = int(os.environ.get("PROBE_ATTEMPTS", "2"))
# Hysteresis. A flapping node is worse for a user than a dead one — it keeps
# reappearing in the list, they connect, and it fails most of the time
# (Amsterdam measured 1-3 successes in 10 while still passing the occasional
# probe). So a node must fail twice running to be pulled, and then succeed
# twice running to come back, which keeps the served list stable instead of
# oscillating with every probe round.
FAILS_TO_DROP = int(os.environ.get("FAILS_TO_DROP", "2"))
PASSES_TO_RESTORE = int(os.environ.get("PASSES_TO_RESTORE", "2"))

# --- alerting -----------------------------------------------------------------
# Pulling a node is the right call, but doing it silently means the owner finds
# out from customers — which is precisely how the Amsterdam week went. The
# prober is the first thing in the system that *knows*, so it is the thing that
# should say so. Uses the separate alerts bot, never the customer-facing one.
ALERTS_BOT_TOKEN = os.environ.get("ALERTS_BOT_TOKEN", "").strip()
ALERTS_CHAT_ID = (
    os.environ.get("ALERTS_CHAT_ID", "").strip()
    or os.environ.get("ADMIN_IDS", "").split(",")[0].strip()
)
# A node that stays dead stops being news after the first message, so it is
# re-announced on this interval instead — otherwise a location quietly missing
# from everyone's list for a week is something nobody is looking at any more.
REMIND_AFTER = float(os.environ.get("PROBE_REMIND_AFTER", str(6 * 3600)))
# The prober runs every 3 minutes; without a cooldown a panel outage would send
# twenty messages an hour and train the owner to ignore the alerts bot.
PROBE_BROKEN_COOLDOWN = float(os.environ.get("PROBE_BROKEN_COOLDOWN", "3600"))
# Names for the hosts the probe sees, so the message reads like the product and
# not like a routing table. Matched on the IP inside the host, because the same
# box appears both bare and as an sslip name.
NODE_NAMES = {
    "144.172.101.217": "🇺🇸 США",
    "78.17.154.225": "🇵🇱 Польша",
    "166.0.28.132": "🇩🇪 Германия",
    "107.189.22.160": "🇳🇱 Нидерланды",
    # Not a Marzban node, but every 🇷🇺→<страна> entry terminates on it, so its
    # death takes out the top of every subscription at once.
    "130.49.143.41": "🇷🇺 Московский релей (все каскады)",
}

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fetch_links(sub_url: str) -> list[str]:
    """Proxy links from the probe account's subscription (base64 or plain)."""
    request = urllib.request.Request(sub_url, headers={"User-Agent": "v2rayNG/1.8.5"})
    with urllib.request.urlopen(request, timeout=20, context=_SSL) as response:
        raw = response.read().decode("utf-8", "replace").strip()
    try:
        raw = base64.b64decode(raw + "===").decode("utf-8", "replace")
    except Exception:
        pass
    return [line.strip() for line in raw.splitlines() if "://" in line]


def parse_vless(uri: str) -> dict | None:
    """Minimal VLESS-Reality parse — the only shape the probe account issues."""
    if not uri.startswith("vless://"):
        return None
    body = uri[len("vless://"):].split("#", 1)[0]
    if "@" not in body:
        return None
    uuid, rest = body.split("@", 1)
    hostport, _, query_str = rest.partition("?")
    host, _, port_str = hostport.partition(":")
    if not host:
        return None
    query = {k: v[0] for k, v in urllib.parse.parse_qs(query_str).items()}
    return {
        "host": host,
        "port": int(port_str or 443),
        "uuid": uuid,
        "sni": query.get("sni", host),
        "pbk": query.get("pbk", ""),
        "sid": query.get("sid", ""),
        "flow": query.get("flow", ""),
        "fp": query.get("fp", "firefox"),
        # Transport matters: probing an XHTTP endpoint with a plain TCP config
        # always fails, and that false negative once removed healthy nodes from
        # every subscription.
        "network": query.get("type", "tcp") or "tcp",
        "path": query.get("path", "/"),
        "mode": query.get("mode", "auto"),
    }


def build_config(node: dict, socks_port: int) -> dict:
    user: dict = {"id": node["uuid"], "encryption": "none"}
    if node["flow"]:
        user["flow"] = node["flow"]
    stream: dict = {
        "network": node["network"],
        "security": "reality",
        "realitySettings": {
            "serverName": node["sni"],
            "fingerprint": node["fp"],
            "publicKey": node["pbk"],
            "shortId": node["sid"],
        },
    }
    if node["network"] == "xhttp":
        stream["xhttpSettings"] = {"path": node["path"], "mode": node["mode"]}
    return {
        "log": {"loglevel": "error"},
        "inbounds": [
            {
                "tag": "probe-in",
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"udp": False},
            }
        ],
        "outbounds": [
            {
                "tag": "probe-out",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {"address": node["host"], "port": node["port"], "users": [user]}
                    ]
                },
                "streamSettings": stream,
            }
        ],
    }


def _probe_remote(node: dict) -> bool:
    """Run one probe on PROBE_FROM_HOST over SSH and report whether it passed.

    The whole exchange is a single ssh invocation carrying the config on stdin,
    so the remote side needs nothing installed beyond xray and curl.
    """
    port = 39000 + (hash(f"{node['host']}:{node['port']}") % 2000)
    config = json.dumps(build_config(node, port))
    script = (
        # .json suffix is required: xray infers the config format from the
        # extension and refuses a plain mktemp file outright.
        f"cfg=$(mktemp --suffix=.json); cat > $cfg; "
        f"{PROBE_FROM_XRAY} run -c $cfg >/dev/null 2>&1 & xp=$!; sleep 3; "
        f"code=$(curl -s -o /dev/null --socks5-hostname 127.0.0.1:{port} "
        f"--max-time {int(PROBE_TIMEOUT)} -w '%{{http_code}}' '{PROBE_URL}' 2>/dev/null); "
        f"kill $xp 2>/dev/null; rm -f $cfg; echo $code"
    )
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
             "-o", "StrictHostKeyChecking=no", PROBE_FROM_HOST, script],
            input=config, capture_output=True, text=True,
            timeout=PROBE_TIMEOUT + 25,
        )
        return "204" in result.stdout
    except Exception:
        # An SSH problem is not a node problem; saying "dead" here would pull
        # healthy exits out of every subscription.
        return True


def probe_node(node: dict) -> bool:
    """True when real traffic completes through this node's tunnel.

    Runs on PROBE_FROM_HOST when set. This matters more than it looks:
    Amsterdam answered every check from the US box with a 200-plus streak
    while failing every single request from a Russian line, so the verdict was
    confidently wrong for days and users kept landing on a dead exit. A node is
    only "up" if it is up *from where the customers are*.
    """
    if PROBE_FROM_HOST:
        return _probe_remote(node)
    port = _free_port()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(build_config(node, port), handle)
        config_path = handle.name
    process = None
    try:
        process = subprocess.Popen(
            [XRAY_BIN, "run", "-c", config_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)  # let xray bind before the first attempt
        for _ in range(PROBE_ATTEMPTS):
            result = subprocess.run(
                [
                    "curl", "-s", "-o", "/dev/null",
                    "--socks5-hostname", f"127.0.0.1:{port}",
                    "--max-time", str(PROBE_TIMEOUT),
                    "-w", "%{http_code}",
                    PROBE_URL,
                ],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT + 5,
            )
            if result.stdout.strip() == "204":
                return True
        return False
    except Exception:
        return False
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        try:
            os.unlink(config_path)
        except OSError:
            pass


def load_previous() -> dict:
    """Last run's verdicts and streaks, so hysteresis survives across runs."""
    try:
        with open(HEALTH_FILE) as handle:
            return json.load(handle)
    except Exception:
        return {}


def apply_hysteresis(previous: dict, fresh: dict[str, bool]) -> tuple[dict, dict]:
    """Fold this round's raw results into stable verdicts.

    Returns (verdicts, streaks). A node keeps its previous verdict until it has
    accumulated enough consecutive results to justify flipping, so one lucky or
    unlucky probe never moves it in or out of everyone's subscription.
    """
    prev_nodes = previous.get("nodes", {})
    prev_streaks = previous.get("streaks", {})
    verdicts: dict[str, bool] = {}
    streaks: dict[str, int] = {}

    for host, passed in fresh.items():
        # streak is positive for consecutive passes, negative for failures
        streak = int(prev_streaks.get(host, 0))
        streak = max(streak, 0) + 1 if passed else min(streak, 0) - 1
        streaks[host] = streak
        # First sighting: trust the probe, there is nothing to be stable about.
        current = prev_nodes.get(host)
        if current is None:
            verdicts[host] = passed
        elif current and streak <= -FAILS_TO_DROP:
            verdicts[host] = False
        elif not current and streak >= PASSES_TO_RESTORE:
            verdicts[host] = True
        else:
            verdicts[host] = bool(current)
    return verdicts, streaks


def node_label(host: str) -> str:
    """Human name for a probed host, falling back to the host itself."""
    for ip, name in NODE_NAMES.items():
        if ip in host:
            return name
    return host


def compose_alert(previous: dict, verdicts: dict[str, bool], now: float) -> tuple[str, dict]:
    """Message describing what changed since the last run, plus new alert state.

    Returns ("", state) when there is nothing to say. Batched deliberately: when
    a whole vantage point goes bad several nodes flip in the same round, and
    five separate messages read like five separate outages.

    Labels are deduplicated because one box is probed under several hostnames
    (bare IP and sslip name) — the owner should see «🇺🇸 США» once, not twice.
    """
    prev_nodes = previous.get("nodes", {})
    notified: dict[str, float] = dict(previous.get("notified_at", {}))

    dropped: list[str] = []
    restored: list[str] = []
    still_down: list[str] = []

    for host, alive in verdicts.items():
        label = node_label(host)
        was = prev_nodes.get(host)
        if not alive and was is not False:  # newly dead (or dead on first sight)
            if label not in dropped:
                dropped.append(label)
            notified[host] = now
        elif alive:
            if was is False and label not in restored:
                restored.append(label)
            notified.pop(host, None)
        elif now - float(notified.get(host, 0)) >= REMIND_AFTER:
            if label not in still_down:
                still_down.append(label)
            notified[host] = now

    # Drop state for hosts that no longer exist, so the file cannot grow forever.
    notified = {host: ts for host, ts in notified.items() if host in verdicts}

    lines: list[str] = []
    if dropped:
        lines.append("🔴 <b>Убраны из выдачи</b>\n" + "\n".join(f"• {n}" for n in dropped))
    if restored:
        lines.append("🟢 <b>Вернулись в выдачу</b>\n" + "\n".join(f"• {n}" for n in restored))
    if still_down:
        lines.append("⏳ <b>Всё ещё не работают</b>\n" + "\n".join(f"• {n}" for n in still_down))
    if not lines:
        return "", notified

    alive_count = sum(1 for ok in verdicts.values() if ok)
    lines.append(
        f"Проверка из России, живых точек входа: {alive_count} из {len(verdicts)}. "
        "Подписки уже отдаются без мёртвых."
    )
    return "\n\n".join(lines), notified


def notify(text: str) -> bool:
    """Best-effort message to the alerts bot. Never raises: a Telegram outage
    must not fail a probe run or hold up the health file."""
    if not ALERTS_BOT_TOKEN or not ALERTS_CHAT_ID:
        return False
    payload = json.dumps({
        "chat_id": ALERTS_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{ALERTS_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except Exception as exc:
        print(f"alert delivery failed: {exc}", file=sys.stderr)
        return False


def report_probe_broken(reason: str) -> None:
    """Announce that the prober itself is down, at most once an hour.

    A blind prober fails open — every node keeps being served, including a dead
    one — so this silence is exactly the state the health checks exist to
    prevent. The cooldown lives in the health file so it survives the run; the
    verdicts inside it are left untouched.
    """
    previous = load_previous()
    now = time.time()
    if now - float(previous.get("broken_notified_at", 0)) < PROBE_BROKEN_COOLDOWN:
        return
    previous["broken_notified_at"] = now
    try:
        tmp_path = f"{HEALTH_FILE}.tmp"
        with open(tmp_path, "w") as handle:
            json.dump(previous, handle)
        os.replace(tmp_path, HEALTH_FILE)
    except Exception as exc:
        print(f"could not persist alert state: {exc}", file=sys.stderr)
    notify(
        "⚠️ <b>Проверка нод не работает</b>\n"
        f"{reason}\n\n"
        "Мёртвая нода сейчас не будет убрана из выдачи автоматически."
    )


def main() -> int:
    if not PROBE_SUB_URL:
        print("PROBE_SUB_URL is not set", file=sys.stderr)
        return 2
    if not os.path.exists(XRAY_BIN):
        print(f"xray binary missing at {XRAY_BIN}", file=sys.stderr)
        return 2
    try:
        links = fetch_links(PROBE_SUB_URL)
    except Exception as exc:
        # Never rewrite the verdicts on a fetch failure: a stale-but-good
        # verdict is far safer than marking every node dead at once. But do say
        # something — a prober that cannot see the panel stops protecting
        # anyone, and that failure is invisible from the outside.
        print(f"subscription fetch failed: {exc}", file=sys.stderr)
        report_probe_broken(f"не удалось получить подписку: {exc}")
        return 1
    links += [
        part.strip()
        for part in PROBE_EXTRA_LINKS.replace(",", "\n").splitlines()
        if part.strip().startswith("vless://")
    ]

    # A node usually publishes several entrypoints (Reality over TCP, XHTTP,
    # …). It is only unreachable if *every* one of them fails, so results are
    # OR-ed per host — assigning per link would let the last one probed
    # overwrite the others and pull a working node out of every subscription.
    fresh: dict[str, bool] = {}
    for uri in links:
        node = parse_vless(uri)
        if node is None:
            continue
        ok = probe_node(node)
        host = node["host"]
        fresh[host] = fresh.get(host, False) or ok

    if not fresh:
        print("no probeable nodes in subscription", file=sys.stderr)
        return 1

    previous = load_previous()
    verdicts, streaks = apply_hysteresis(previous, fresh)
    text, notified = compose_alert(previous, verdicts, time.time())
    payload = {
        "checked_at": int(time.time()),
        "nodes": verdicts,
        "streaks": streaks,
        "notified_at": notified,
    }
    tmp_path = f"{HEALTH_FILE}.tmp"
    with open(tmp_path, "w") as handle:
        json.dump(payload, handle)
    os.replace(tmp_path, HEALTH_FILE)  # atomic: readers never see a half file

    # After the write, deliberately: the subscription must stop serving a dead
    # exit even if Telegram is unreachable. Logged as well as sent, so the
    # journal still shows what the owner was told when delivery fails.
    if text:
        print(f"--- alert ---\n{text}\n-------------")
        notify(text)

    for host in sorted(fresh):
        this_run = "pass" if fresh[host] else "FAIL"
        served = "OK  " if verdicts[host] else "DEAD"
        print(f"{served} {host}  (this run: {this_run}, streak {streaks[host]:+d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
