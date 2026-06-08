#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.client_profiles import build_happ_xray_profile, dumps_happ_xray_profile, endpoints_from_dicts


def _read_endpoints(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, dict):
        payload = payload.get("endpoints")
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise SystemExit("Input must be a JSON array or an object with an 'endpoints' array.")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Happ/Xray JSON subscription profile from Reality/Hysteria2/SS/Trojan endpoints."
    )
    parser.add_argument("input", type=Path, help="JSON file with endpoint definitions.")
    parser.add_argument("-o", "--output", type=Path, help="Where to write the generated profile. Defaults to stdout.")
    parser.add_argument("--remarks", default="UnLock VPN", help="Profile title shown in the client.")
    parser.add_argument("--no-auto", action="store_true", help="Disable Xray balancer/burstObservatory auto selection.")
    parser.add_argument("--compact", action="store_true", help="Write minified JSON.")
    args = parser.parse_args()

    endpoints = endpoints_from_dicts(_read_endpoints(args.input))
    profile = build_happ_xray_profile(
        endpoints,
        remarks=args.remarks,
        auto_select=not args.no_auto,
    )
    output = dumps_happ_xray_profile(profile, pretty=not args.compact)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
