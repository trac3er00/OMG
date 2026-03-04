#!/usr/bin/env python3
"""Check that standalone/OMG-first naming rules are preserved."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

# Paths where legacy aliases are explicitly allowed.
ALLOW_COMPAT_CLI = {
    ROOT / "commands" / "OMG:compat.md",
    ROOT / "tests" / "scripts" / "test_omg_cli.py",
    ROOT / "tests" / "scripts" / "test_standalone_clean_check.py",
    ROOT / "scripts" / "check-omg-standalone-clean.py",
    ROOT / ".github" / "workflows" / "omg-compat-gate.yml",
}

ALLOW_LEGACY_MIGRATOR = {
    ROOT / "scripts" / "migrate-legacy.py",
    ROOT / "tests" / "e2e" / "test_standalone_ga.py",
    ROOT / "scripts" / "check-omg-standalone-clean.py",
}

ALLOW_LEGACY_SNAPSHOT_CHECKER = {
    ROOT / "scripts" / "check-omg-contract-snapshot.py",
    ROOT / "tests" / "scripts" / "test_compat_snapshot_check.py",
    ROOT / "scripts" / "check-omg-standalone-clean.py",
}

ALLOW_LEGACY_RUNTIME_IMPORT = {
    ROOT / "tests" / "scripts" / "test_standalone_clean_check.py",
    ROOT / "scripts" / "check-omg-standalone-clean.py",
}

SCAN_GLOBS = [
    "README.md",
    "OMG-setup.sh",
    "install.sh",
    "runtime/**/*.py",
    "hooks/**/*.py",
    "scripts/**/*.py",
    "commands/**/*.md",
    ".github/workflows/**/*.yml",
    "tests/**/*.py",
]


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in SCAN_GLOBS:
        files.extend(p for p in root.glob(pattern) if p.is_file())
    # deterministic order
    return sorted(set(files))


def _contains(path: Path, token: str) -> bool:
    return token in path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OMG standalone naming hygiene")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()

    violations: list[str] = []

    deprecated_workflow = root / ".github" / "workflows" / "compat-gate.yml"
    if deprecated_workflow.exists():
        violations.append(f"deprecated workflow exists: {deprecated_workflow.relative_to(root)}")

    for path in _iter_files(root):
        rel = path.relative_to(root)

        if _contains(path, "python3 scripts/omg.py compat ") or _contains(path, "python3 scripts/omg.py omc "):
            if path not in ALLOW_COMPAT_CLI:
                violations.append(f"{rel}: legacy CLI namespace used outside allowlist")

        if _contains(path, "migrate-legacy.py"):
            if path not in ALLOW_LEGACY_MIGRATOR:
                violations.append(f"{rel}: legacy migrator path reference outside allowlist")

        if _contains(path, "check-omg-contract-snapshot.py"):
            if path not in ALLOW_LEGACY_SNAPSHOT_CHECKER:
                violations.append(f"{rel}: legacy snapshot checker reference outside allowlist")

        if _contains(path, "runtime.legacy_compat"):
            if path not in ALLOW_LEGACY_RUNTIME_IMPORT:
                violations.append(f"{rel}: legacy runtime import outside allowlist")

    if violations:
        print(json.dumps({"status": "error", "violations": violations}, indent=2))
        return 1

    print(json.dumps({"status": "ok", "message": "standalone naming check passed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
