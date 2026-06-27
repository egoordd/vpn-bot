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
  MARZBAN_BASE   e.g. https://144.172.101.217.sslip.io:8443
  US_HY2_PASS    Hysteria2 password on the US node
  NL_HY2_PASS    Hysteria2 password on the NL node
  LISTEN_PORT    default 8090 (bind 127.0.0.1; nginx proxies a public path)
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARZBAN_BASE = os.environ.get("MARZBAN_BASE", "https://144.172.101.217.sslip.io:8443").rstrip("/")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8090"))
BIND_HOST = os.environ.get("BIND_HOST", "127.0.0.1")
CERT_FILE = os.environ.get("CERT_FILE", "")  # when set -> serve HTTPS on BIND_HOST
KEY_FILE = os.environ.get("KEY_FILE", "")
# Public origin used to build the /sub/<token> URL embedded in the Happ deep
# link. Empty -> derive from the request Host header (correct in prod).
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "").rstrip("/")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# Display name clients show for the subscription (Happ reads `profile-title`,
# base64 UTF-8, max 25 chars). Without it Happ shows the default "subscription".
SUB_TITLE = os.environ.get("SUB_TITLE", "UnLock VPN")
PROFILE_TITLE_HEADER = "base64:" + base64.b64encode(SUB_TITLE.encode("utf-8")).decode("ascii")

# vless host -> location + its Hysteria2 endpoint
NODES = {
    "144.172.101.217.sslip.io": {
        "flag": "🇺🇸", "name": "США",
        "hy2_host": "144.172.101.217.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("US_HY2_PASS", ""),
    },
    "107.189.22.160.sslip.io": {
        "flag": "🇳🇱", "name": "Нидерланды",
        "hy2_host": "107.189.22.160.sslip.io", "hy2_port": 443,
        "hy2_pass": os.environ.get("NL_HY2_PASS", ""),
    },
}

# The gateway calls our own Marzban panel (same host in prod), so TLS
# verification is unnecessary here and trips on the own-domain sslip cert.
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


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


def _fetch_marzban_sub(token: str) -> tuple[str, str | None] | None:
    """Returns (decoded_uris_text, userinfo_header) or None if invalid."""
    url = f"{MARZBAN_BASE}/sub/{token}"
    req = urllib.request.Request(url, headers={"User-Agent": "v2rayNG/1.8.5"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
            raw = resp.read().decode("utf-8", "replace").strip()
            userinfo = resp.headers.get("subscription-userinfo")
    except Exception:
        return None
    try:
        decoded = base64.b64decode(raw + "===").decode("utf-8", "replace")
    except Exception:
        decoded = raw
    return decoded, userinfo


def combine_links(decoded: str) -> list[str]:
    """Pass through every proxy link Marzban issued and append each node's
    Hysteria2 endpoint once (after the node's first link), preserving order.

    Protocol-agnostic: vless, trojan, shadowsocks etc. all flow through, so a
    new panel inbound needs no gateway change. Hy2 is deduped per node so a
    location that exposes both VLESS and Trojan doesn't list Hysteria2 twice.
    """
    proxy_uris = [line.strip() for line in decoded.splitlines() if "://" in line.strip()]
    combined: list[str] = []
    hy2_done: set[str] = set()
    for uri in proxy_uris:
        combined.append(uri)
        host = _uri_host(uri)
        node = NODES.get(host) if host else None
        if node and node["hy2_pass"] and host not in hy2_done:
            combined.append(_hy2_uri(node))
            hy2_done.add(host)
    return combined


def build_combined(token: str) -> tuple[str, str | None] | None:
    fetched = _fetch_marzban_sub(token)
    if fetched is None:
        return None
    decoded, userinfo = fetched
    combined = combine_links(decoded)
    if not combined:
        return "", userinfo

    payload = base64.b64encode("\n".join(combined).encode("utf-8")).decode("ascii")
    return payload, userinfo


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

    def log_message(self, *args):  # silence default logging
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/health", "/healthz"):
            self._send(200, b"ok", "text/plain")
            return
        happ_prefix = "/happ/"
        if path.startswith(happ_prefix):
            token = path[len(happ_prefix):].split("/", 1)[0]
            if not _TOKEN_RE.match(token):
                self._send(404, b"not found", "text/plain")
                return
            base = PUBLIC_BASE or f"https://{self.headers.get('Host', '')}".rstrip("/")
            page = happ_redirect_page(f"{base}/sub/{token}")
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        prefix = "/sub/"
        if not path.startswith(prefix):
            self._send(404, b"not found", "text/plain")
            return
        token = path[len(prefix):].split("/", 1)[0]
        if not token:
            self._send(404, b"not found", "text/plain")
            return
        result = build_combined(token)
        if result is None:
            self._send(404, b"invalid subscription", "text/plain")
            return
        payload, userinfo = result
        extra = {"profile-title": PROFILE_TITLE_HEADER}
        if userinfo:
            extra["subscription-userinfo"] = userinfo
        self._send(200, payload.encode("ascii"), "text/plain; charset=utf-8", extra)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Profile-Update-Interval", "12")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((BIND_HOST, LISTEN_PORT), Handler)
    scheme = "http"
    if CERT_FILE and KEY_FILE:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    print(f"sub-gateway on {scheme}://{BIND_HOST}:{LISTEN_PORT}, marzban={MARZBAN_BASE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
