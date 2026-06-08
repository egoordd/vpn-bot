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


def _int_env(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


def _seed_required_app_env(db_url: str) -> None:
    os.environ.setdefault("BOT_TOKEN", "probe:token")
    os.environ.setdefault("DATABASE_URL", db_url)
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("WG_SERVER_PUBLIC_KEY", "probe")
    os.environ.setdefault("WG_SERVER_ENDPOINT", "127.0.0.1:51820")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Register an existing Remnawave node as a manual DB node.")
    parser.add_argument("--ip", default=_env("REMNAWAVE_STATIC_NODE_IP"))
    parser.add_argument("--panel-node-id", default=_env("REMNAWAVE_STATIC_PANEL_NODE_ID"))
    parser.add_argument("--region", default=_env("REMNAWAVE_STATIC_NODE_REGION", _env("VULTR_DEFAULT_REGION", "ams")))
    parser.add_argument("--capacity", type=int, default=_int_env("REMNAWAVE_STATIC_NODE_CAPACITY", 50))
    parser.add_argument("--name", default=_env("REMNAWAVE_STATIC_NODE_NAME", "manual-remnawave-node"))
    parser.add_argument("--db-url", default=_env("DATABASE_URL", "sqlite+aiosqlite:///./static_node.sqlite3"))
    parser.add_argument("--create-schema", action="store_true", help="Create tables first for local smoke DBs.")
    args = parser.parse_args()

    missing = []
    if not args.ip:
        missing.append("--ip or REMNAWAVE_STATIC_NODE_IP")
    if not args.panel_node_id:
        missing.append("--panel-node-id or REMNAWAVE_STATIC_PANEL_NODE_ID")
    if missing:
        print(_json_dump({"ok": False, "missing": missing}))
        return 2

    _seed_required_app_env(args.db_url)

    from database.models import Base
    from services.autoscaler import StaticNodeRegistration, register_static_node

    engine = create_async_engine(args.db_url, echo=False)
    session_pool = async_sessionmaker(engine, expire_on_commit=False)

    try:
        if args.create_schema:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

        async with session_pool() as session:
            node = await register_static_node(
                session,
                StaticNodeRegistration(
                    name=args.name,
                    ip_address=args.ip,
                    panel_node_id=args.panel_node_id,
                    region=args.region,
                    capacity=args.capacity,
                ),
            )

        print(
            _json_dump(
                {
                    "ok": True,
                    "node": {
                        "id": node.id,
                        "name": node.name,
                        "provider": node.provider,
                        "ipAddress": node.ip_address,
                        "panelNodeId": node.panel_node_id,
                        "region": node.region,
                        "capacity": node.capacity,
                        "status": node.status,
                    },
                }
            )
        )
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
