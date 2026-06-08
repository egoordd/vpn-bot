#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in _env(name).split(",") if item.strip()]


def _expire_at(days: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    base_url: str,
    path: str,
    token: str,
    *,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with session.request(method, url, headers=headers, json=json_payload) as response:
        text = await response.text()
        try:
            body = json.loads(text) if text else {}
        except json.JSONDecodeError:
            body = {"raw": text}
        return {"method": method, "path": path, "status": response.status, "body": body}


def _unwrap(body: Any) -> Any:
    if isinstance(body, dict) and "response" in body:
        return body["response"]
    return body


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe live Remnawave API contract without hiding raw responses.")
    parser.add_argument("--create-user", action="store_true", help="Create a short-lived test user and delete it.")
    parser.add_argument("--keep-user", action="store_true", help="Do not delete created test user.")
    parser.add_argument("--yes", action="store_true", help="Required with --create-user.")
    parser.add_argument("--username", default=f"codex_probe_{int(time.time())}")
    args = parser.parse_args()

    base_url = _env("REMNAWAVE_API_URL")
    token = _env("REMNAWAVE_API_TOKEN")
    if not base_url or not token:
        print("REMNAWAVE_API_URL and REMNAWAVE_API_TOKEN are required.")
        return 2
    if args.create_user and not args.yes:
        print("--create-user requires --yes because it writes to the live panel.")
        return 2

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        probes: list[dict[str, Any]] = []
        for path in (
            "/api/auth/status",
            "/api/keygen",
            "/api/config-profiles",
            "/api/config-profiles/inbounds",
            "/api/internal-squads",
        ):
            probes.append(await _request(session, "GET", base_url, path, token))

        created_uuid = ""
        if args.create_user:
            active_internal_squads = _csv_env("REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS")
            payload = {
                "username": args.username,
                "status": "ACTIVE",
                "trafficLimitBytes": 1024**3,
                "trafficLimitStrategy": _env("REMNAWAVE_DEFAULT_TRAFFIC_RESET_STRATEGY", "NO_RESET"),
                "expireAt": _expire_at(),
                "description": "codex live contract probe",
                "hwidDeviceLimit": 1,
            }
            if active_internal_squads:
                payload["activeInternalSquads"] = active_internal_squads
            create_result = await _request(session, "POST", base_url, "/api/users", token, json_payload=payload)
            probes.append({**create_result, "requestPayload": payload})

            created = _unwrap(create_result["body"])
            if isinstance(created, dict):
                created_uuid = str(created.get("uuid") or "")

            probes.append(await _request(session, "GET", base_url, f"/api/users/by-username/{args.username}", token))
            probes.append(
                await _request(session, "GET", base_url, f"/api/subscriptions/by-username/{args.username}", token)
            )

            if created_uuid and not args.keep_user:
                probes.append(await _request(session, "DELETE", base_url, f"/api/users/{created_uuid}", token))

    print(_json_dump({"ok": True, "baseUrl": base_url, "probes": probes}))
    failed = [item for item in probes if int(item["status"]) >= 400]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
