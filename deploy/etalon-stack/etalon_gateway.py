"""Шлюз подписок Etalon VPN — собственная установка заказчика (15.10.2026).

Берёт подписку пользователя у своей панели Marzban и отдаёт её клиенту:
- Happ — JSON-конфиги xray: «⚡️ Авто-выбор» (балансировщик между странами),
  «🇷🇺 Режим РУ-сервисов» и по пункту на страну (xray_json.build_json_subscription);
- остальным приложениям — обычный base64-список ссылок;
- истёкшая подписка — пустой список (Marzban отдаёт ссылки и после срока).

Только стандартная библиотека Python. Слушает 127.0.0.1 (по умолчанию :2096); снаружи до него
доходят через nginx на московском входе. Настройки — переменные окружения GW_* (etalon-gateway.env).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xray_json import build_json_subscription

log = logging.getLogger("etalon-gateway")

LISTEN = os.environ.get("GW_LISTEN", "127.0.0.1:2096")
MARZBAN = os.environ.get("GW_MARZBAN", "http://127.0.0.1:8000").rstrip("/")
TITLE = os.environ.get("GW_TITLE", "Etalon VPN")
AUTO_TITLE = os.environ.get("GW_AUTO_TITLE", "⚡️ Авто-выбор")
SUPPORT_URL = os.environ.get("GW_SUPPORT_URL", "")
WEB_URL = os.environ.get("GW_WEB_URL", "")
UPDATE_HOURS = os.environ.get("GW_UPDATE_HOURS", "12")

SUB_PATH = re.compile(r"^/sub/([A-Za-z0-9_\-=]{10,300})/?$")
JSON_CLIENTS = ("happ",)
LINK_SCHEMES = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://")


def fetch_upstream(token: str) -> tuple[list[str], str | None] | None:
    """Ссылки пользователя и его subscription-userinfo из Marzban; None — такого токена нет."""
    req = urllib.request.Request(f"{MARZBAN}/sub/{token}", headers={"User-Agent": "v2rayN/7.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", "replace").strip()
            userinfo = resp.headers.get("subscription-userinfo")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return None
        raise
    try:
        text = base64.b64decode(raw + "===").decode("utf-8", "replace")
    except ValueError:
        text = raw
    links = [line.strip() for line in text.splitlines() if line.strip().startswith(LINK_SCHEMES)]
    return links, userinfo


def expired(userinfo: str | None) -> bool:
    match = re.search(r"expire=(\d+)", userinfo or "")
    return bool(match) and 0 < int(match.group(1)) < time.time()


def _b64(text: str) -> str:
    return "base64:" + base64.b64encode(text.encode()).decode()


def render(path: str, user_agent: str) -> tuple[int, dict[str, str], bytes]:
    """(статус, заголовки, тело) ответа на GET path."""
    match = SUB_PATH.match(path.split("?", 1)[0])
    if not match:
        return 404, {"Content-Type": "text/plain"}, b"not found\n"
    upstream = fetch_upstream(match.group(1))
    if upstream is None:
        return 404, {"Content-Type": "text/plain"}, b"not found\n"
    links, userinfo = upstream
    if expired(userinfo):
        links = []
    headers = {
        "Cache-Control": "no-store",
        "profile-title": _b64(TITLE),
        "profile-update-interval": UPDATE_HOURS,
    }
    if userinfo:
        headers["subscription-userinfo"] = userinfo
    if SUPPORT_URL:
        headers["support-url"] = SUPPORT_URL
    if WEB_URL:
        headers["profile-web-page-url"] = WEB_URL
    configs = []
    if links and any(client in user_agent.lower() for client in JSON_CLIENTS):
        configs = build_json_subscription(links, split=True, auto_remarks=AUTO_TITLE)
    if configs:
        headers["Content-Type"] = "application/json; charset=utf-8"
        return 200, headers, json.dumps(configs, ensure_ascii=False, separators=(",", ":")).encode()
    headers["Content-Type"] = "text/plain; charset=utf-8"
    return 200, headers, base64.b64encode("\n".join(links).encode())


class Handler(BaseHTTPRequestHandler):
    server_version = "nginx"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 — имя задаёт http.server
        try:
            status, headers, body = render(self.path, self.headers.get("User-Agent", ""))
        except Exception:
            log.exception("subscription request failed")
            status, headers, body = 502, {"Content-Type": "text/plain"}, b"temporarily unavailable\n"
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # Токен подписки в журнал не пишем — только статус и приложение.
        log.info("%s %s", args[1] if len(args) > 1 else "-", self.headers.get("User-Agent", "-")[:40])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, port = LISTEN.rsplit(":", 1)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
