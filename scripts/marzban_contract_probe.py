#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.marzban_client import MarzbanClient, MarzbanNotFoundError


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _parse_inbound(value: str) -> tuple[str, str]:
    protocol, separator, tag = value.partition("=")
    if not separator or not protocol.strip() or not tag.strip():
        raise argparse.ArgumentTypeError("inbound must use protocol=tag format")
    return protocol.strip(), tag.strip()


def _protocols(items: list[str]) -> list[str]:
    return [item.split(":", 1)[0] for item in items]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe live Marzban API contract through project client.")
    parser.add_argument("--base-url", default=_env("MARZBAN_API_URL"))
    parser.add_argument("--access-token", default=_env("MARZBAN_ACCESS_TOKEN"))
    parser.add_argument("--username", default=_env("MARZBAN_USERNAME"))
    parser.add_argument("--password", default=_env("MARZBAN_PASSWORD"))
    parser.add_argument("--create-user", action="store_true", help="Create, read, modify, and delete a probe user.")
    parser.add_argument("--keep-user", action="store_true", help="Keep created probe user.")
    parser.add_argument("--yes", action="store_true", help="Required with --create-user.")
    parser.add_argument("--probe-username", default=f"codex_marzban_probe_{int(time.time())}")
    parser.add_argument("--proxy", action="append", default=["vless"], help="Proxy protocol to enable; repeatable.")
    parser.add_argument(
        "--inbound",
        action="append",
        type=_parse_inbound,
        default=[("vless", "VLESS Reality 443")],
        help="Inbound mapping in protocol=tag format; repeatable.",
    )
    parser.add_argument("--print-links", action="store_true", help="Print live client links in output.")
    args = parser.parse_args()

    if not args.base_url:
        print("MARZBAN_API_URL or --base-url is required.")
        return 2
    if not args.access_token and not (args.username and args.password):
        print("MARZBAN_ACCESS_TOKEN or MARZBAN_USERNAME/MARZBAN_PASSWORD is required.")
        return 2
    if args.create_user and not args.yes:
        print("--create-user requires --yes because it writes to the live panel.")
        return 2

    client = MarzbanClient(
        base_url=args.base_url,
        access_token=args.access_token or None,
        username=args.username or None,
        password=args.password or None,
    )
    probes: dict[str, Any] = {}

    try:
        probes["system"] = await client.get_system()
        probes["inbounds"] = await client.get_inbounds()

        if args.create_user:
            probes["createUser"] = await _create_user_probe(client, args)
    finally:
        await client.close()

    print(_json_dump({"ok": True, "baseUrl": args.base_url, "probes": probes}))
    return 0


async def _create_user_probe(client: MarzbanClient, args: argparse.Namespace) -> dict[str, Any]:
    proxies = {protocol: {} for protocol in args.proxy}
    inbounds: dict[str, list[str]] = {}
    for protocol, tag in args.inbound:
        inbounds.setdefault(protocol, []).append(tag)

    try:
        await client.delete_user(args.probe_username)
    except MarzbanNotFoundError:
        pass

    created = await client.create_user(
        username=args.probe_username,
        expire_at=int(time.time()) + 3600,
        data_limit_bytes=1024**3,
        proxies=proxies,
        inbounds=inbounds,
        data_limit_reset_strategy="no_reset",
        note="codex marzban contract probe",
    )
    fetched = await client.get_user(args.probe_username)
    modified = await client.modify_user(
        args.probe_username,
        expire_at=int(time.time()) + 7200,
        data_limit_bytes=2 * 1024**3,
        proxies=proxies,
        inbounds=inbounds,
        data_limit_reset_strategy="no_reset",
        status="active",
        note="codex marzban contract probe updated",
    )

    deleted = False
    if not args.keep_user:
        await client.delete_user(args.probe_username)
        deleted = True

    result = {
        "username": created.username,
        "createdStatus": created.status,
        "subscriptionUrl": created.subscription_url,
        "fetchedHasSubscription": bool(fetched.subscription_url),
        "modifiedDataLimitBytes": modified.data_limit_bytes,
        "linkProtocols": _protocols(fetched.links),
        "deleted": deleted,
    }
    if args.print_links:
        result["links"] = fetched.links
    return result


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
