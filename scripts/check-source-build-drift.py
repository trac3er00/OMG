#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys


CURATED_MODULES = [
    "runtime/business_workflow.py",
    "runtime/cli_provider.py",
    "runtime/compat.py",
    "runtime/custom_agent_loader.py",
    "runtime/dispatcher.py",
    "runtime/ecosystem.py",
    "runtime/legacy_compat.py",
    "runtime/mcp_config_writers.py",
    "runtime/mcp_lifecycle.py",
    "runtime/mcp_memory_server.py",
    "runtime/memory_store.py",
    "runtime/subagent_dispatcher.py",
    "runtime/team_router.py",
    "runtime/tmux_session_manager.py",
    "hooks/_agent_registry.py",
    "hooks/prompt-enhancer.py",
    "hooks/setup_wizard.py",
    "hooks/stop_dispatcher.py",
]

ALLOWLIST_BUILD_ONLY: set[str] = set()
ALLOWLIST_SOURCE_ONLY: set[str] = set()


def _build_side_path(root: Path, relative_path: str) -> Path:
    return root / "build" / "lib" / relative_path


def build_drift_report(root_dir: str) -> dict[str, object]:
    root = Path(root_dir).resolve()
    checked_modules: list[str] = []
    build_only: list[str] = []
    source_only: list[str] = []
    aligned: list[str] = []

    for relative_path in CURATED_MODULES:
        source_path = root / relative_path
        build_path = _build_side_path(root, relative_path)
        checked_modules.append(relative_path)

        source_exists = source_path.exists()
        build_exists = build_path.exists()

        if source_exists and build_exists:
            aligned.append(relative_path)
        elif build_exists and relative_path not in ALLOWLIST_BUILD_ONLY:
            build_only.append(relative_path)
        elif source_exists and relative_path not in ALLOWLIST_SOURCE_ONLY:
            source_only.append(relative_path)

    status = "ok" if not build_only and not source_only else "error"
    return {
        "schema": "SourceBuildDriftReport",
        "status": status,
        "checked_modules": checked_modules,
        "aligned_modules": aligned,
        "build_only_unallowlisted": build_only,
        "source_only_unallowlisted": source_only,
        "allowlist": {
            "build_only": sorted(ALLOWLIST_BUILD_ONLY),
            "source_only": sorted(ALLOWLIST_SOURCE_ONLY),
        },
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report = build_drift_report(str(root))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())
