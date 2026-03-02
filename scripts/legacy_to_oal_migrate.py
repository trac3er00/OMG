#!/usr/bin/env python3
"""CLI utility: migrate legacy state into canonical `.oal` layout."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hooks.state_migration import migrate_legacy_to_oal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy state to .oal")
    parser.add_argument("--project-dir", default=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    args = parser.parse_args()

    report = migrate_legacy_to_oal(args.project_dir)
    print(json.dumps(report, indent=2))
    return 0 if report.get("result") in {"ok", "no_legacy"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
