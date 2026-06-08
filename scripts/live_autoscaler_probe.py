#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _csv(name: str) -> list[str]:
    return [item.strip() for item in _env(name).split(",") if item.strip()]


def _seed_required_app_env() -> None:
    os.environ.setdefault("BOT_TOKEN", "probe:token")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./live_autoscaler_probe.sqlite3")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("WG_SERVER_PUBLIC_KEY", "probe")
    os.environ.setdefault("WG_SERVER_ENDPOINT", "127.0.0.1:51820")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Billable live smoke: create Vultr instance, register Remnawave node, then delete both."
    )
    parser.add_argument("--yes", action="store_true", help="Required. This creates a billable Vultr instance.")
    parser.add_argument("--keep", action="store_true", help="Do not delete the created instance/node.")
    parser.add_argument("--region", default=_env("VULTR_DEFAULT_REGION", "ams"))
    parser.add_argument("--country-code", default=_env("REMNAWAVE_NODE_COUNTRY_CODE", "XX"))
    parser.add_argument("--name", default="codex-live-autoscaler-probe")
    parser.add_argument("--db-url", default="sqlite+aiosqlite:///./live_autoscaler_probe.sqlite3")
    args = parser.parse_args()

    if not args.yes:
        print("--yes is required because this creates a billable Vultr instance.")
        return 2

    required = [
        "REMNAWAVE_API_URL",
        "REMNAWAVE_API_TOKEN",
        "REMNAWAVE_NODE_CONFIG_PROFILE_UUID",
        "REMNAWAVE_NODE_INBOUND_UUIDS",
        "REMNAWAVE_HOST_PORT",
        "VULTR_API_TOKEN",
        "VULTR_DEFAULT_PLAN",
        "VULTR_DEFAULT_OS_ID",
    ]
    missing = [name for name in required if not _env(name)]
    if missing:
        print(_json_dump({"ok": False, "missing": missing}))
        return 2

    _seed_required_app_env()
    from database.models import Base
    from services.autoscaler import ProvisionNodeRequest, decommission_vultr_node, provision_vultr_node

    engine = create_async_engine(args.db_url, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    created_node_id: int | None = None
    result: dict[str, Any] = {"ok": False, "created": None, "deleted": False}

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        request = ProvisionNodeRequest(
            tier="premium",
            region=args.region,
            capacity=int(_env("VULTR_NODE_CAPACITY", "50")),
            plan=_env("VULTR_DEFAULT_PLAN"),
            os_id=int(_env("VULTR_DEFAULT_OS_ID")),
            name=args.name,
            country_code=args.country_code,
            config_profile_uuid=_env("REMNAWAVE_NODE_CONFIG_PROFILE_UUID"),
            active_inbound_uuids=_csv("REMNAWAVE_NODE_INBOUND_UUIDS"),
            node_port=int(_env("REMNAWAVE_NODE_PORT", "2222")),
            host_port=int(_env("REMNAWAVE_HOST_PORT")),
            ssh_key_ids=_csv("VULTR_SSH_KEY_IDS"),
        )

        async with session_pool() as session:
            node = await provision_vultr_node(session, request)
            created_node_id = node.id
            result["created"] = {
                "id": node.id,
                "name": node.name,
                "ipAddress": node.ip_address,
                "providerInstanceId": node.provider_instance_id,
                "panelNodeId": node.panel_node_id,
                "region": node.region,
            }

            if not args.keep:
                result["deleted"] = await decommission_vultr_node(session, node.id)

        result["ok"] = True
        print(_json_dump(result))
        return 0
    except Exception as exc:
        result["error"] = repr(exc)
        if created_node_id is not None and not args.keep:
            try:
                async with session_pool() as session:
                    result["deletedAfterError"] = await decommission_vultr_node(session, created_node_id)
            except Exception as cleanup_exc:
                result["cleanupError"] = repr(cleanup_exc)
        print(_json_dump(result))
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
