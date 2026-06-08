#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import aiohttp


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    base_url: str,
    path: str,
    token: str,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with session.request(method, url, headers=headers) as response:
        text = await response.text()
        try:
            body = json.loads(text) if text else {}
        except json.JSONDecodeError:
            body = {"raw": text}
        return {"method": method, "path": path, "status": response.status, "body": body}


def _contains(items: list[dict[str, Any]], key: str, expected: str) -> bool:
    if not expected:
        return False
    return any(str(item.get(key)) == expected for item in items)


async def main() -> int:
    base_url = _env("VULTR_API_URL", "https://api.vultr.com/v2")
    token = _env("VULTR_API_TOKEN")
    if not token:
        print("VULTR_API_TOKEN is required.")
        return 2

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        probes = [
            await _request(session, "GET", base_url, "/account", token),
            await _request(session, "GET", base_url, "/regions", token),
            await _request(session, "GET", base_url, "/plans?type=vc2", token),
            await _request(session, "GET", base_url, "/os", token),
            await _request(session, "GET", base_url, "/ssh-keys", token),
        ]

    regions = probes[1]["body"].get("regions") if isinstance(probes[1]["body"], dict) else []
    plans = probes[2]["body"].get("plans") if isinstance(probes[2]["body"], dict) else []
    os_items = probes[3]["body"].get("os") if isinstance(probes[3]["body"], dict) else []
    ssh_keys = probes[4]["body"].get("ssh_keys") if isinstance(probes[4]["body"], dict) else []

    default_os_id = _env("VULTR_DEFAULT_OS_ID")
    ssh_key_ids = [item.strip() for item in _env("VULTR_SSH_KEY_IDS").split(",") if item.strip()]
    checks = {
        "defaultRegionExists": _contains(regions or [], "id", _env("VULTR_DEFAULT_REGION")),
        "defaultPlanExists": _contains(plans or [], "id", _env("VULTR_DEFAULT_PLAN")),
        "defaultOsExists": _contains(os_items or [], "id", default_os_id),
        "configuredSshKeysExist": all(_contains(ssh_keys or [], "id", key_id) for key_id in ssh_key_ids),
    }

    print(_json_dump({"ok": True, "baseUrl": base_url, "checks": checks, "probes": probes}))
    failed_http = [item for item in probes if int(item["status"]) >= 400]
    failed_checks = [key for key, value in checks.items() if not value and key != "configuredSshKeysExist"]
    return 1 if failed_http or failed_checks else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
