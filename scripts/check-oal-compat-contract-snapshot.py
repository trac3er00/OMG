#!/usr/bin/env python3
"""Validate committed OAL compatibility snapshot against runtime contracts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.compat import (  # noqa: E402
    CONTRACT_SNAPSHOT_SCHEMA,
    CONTRACT_SNAPSHOT_VERSION,
    DEFAULT_CONTRACT_SNAPSHOT_PATH,
    LEGACY_CONTRACT_SNAPSHOT_PATH,
    build_contract_snapshot_payload,
    migrate_contract_snapshot_payload,
)


def _load_snapshot(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("snapshot must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OAL compatibility contract snapshot drift")
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--strict-version", action="store_true")
    args = parser.parse_args()

    if args.snapshot:
        snapshot_path = Path(args.snapshot)
    else:
        primary = ROOT / DEFAULT_CONTRACT_SNAPSHOT_PATH
        legacy = ROOT / LEGACY_CONTRACT_SNAPSHOT_PATH
        snapshot_path = primary if primary.exists() else legacy

    if not snapshot_path.exists():
        print(
            json.dumps(
                {"status": "error", "message": f"snapshot not found: {snapshot_path}"},
                indent=2,
            )
        )
        return 2

    try:
        current = _load_snapshot(snapshot_path)
    except Exception as exc:
        print(json.dumps({"status": "error", "message": f"invalid snapshot json: {exc}"}, indent=2))
        return 2

    migrated, migrations = migrate_contract_snapshot_payload(current)
    expected = build_contract_snapshot_payload(include_generated_at=False)

    if migrated.get("schema") != CONTRACT_SNAPSHOT_SCHEMA:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "snapshot schema mismatch",
                    "expected_schema": CONTRACT_SNAPSHOT_SCHEMA,
                    "actual_schema": migrated.get("schema"),
                },
                indent=2,
            )
        )
        return 3

    if args.strict_version and current.get("contract_version") != CONTRACT_SNAPSHOT_VERSION:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "snapshot contract_version mismatch (strict)",
                    "expected_version": CONTRACT_SNAPSHOT_VERSION,
                    "actual_version": current.get("contract_version"),
                },
                indent=2,
            )
        )
        return 3

    if migrated.get("contract_version") != CONTRACT_SNAPSHOT_VERSION:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "snapshot contract_version unsupported",
                    "expected_version": CONTRACT_SNAPSHOT_VERSION,
                    "actual_version": migrated.get("contract_version"),
                },
                indent=2,
            )
        )
        return 3

    if migrated.get("count") != expected.get("count") or migrated.get("contracts") != expected.get("contracts"):
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "snapshot drift detected",
                    "expected_count": expected.get("count"),
                    "actual_count": migrated.get("count"),
                    "migrations_applied": migrations,
                },
                indent=2,
            )
        )
        return 3

    print(
        json.dumps(
            {
                "status": "ok",
                "message": "snapshot matches runtime contracts",
                "contract_version": CONTRACT_SNAPSHOT_VERSION,
                "migrations_applied": migrations,
                "snapshot": str(snapshot_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

