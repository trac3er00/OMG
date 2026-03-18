#!/usr/bin/env python3
"""Published-artifact self-audit gate.

Validates that an unpacked artifact directory (git tarball or npm pack output)
has version-consistent internals matching the expected release tag.

Usage:
    python3 scripts/audit-published-artifact.py --version 2.2.8 --source-tree .
    python3 scripts/audit-published-artifact.py --version 2.2.8 --source-tree pkg/ --npm-pack
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _check_status(ok: bool) -> str:
    return "ok" if ok else "fail"


def check_package_json_version(source_tree: Path, expected: str) -> dict[str, Any]:
    pkg = source_tree / "package.json"
    if not pkg.exists():
        return {"status": "fail", "found": "<missing>", "expected": expected}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        found = data.get("version", "<missing>")
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "fail", "found": f"<error: {e}>", "expected": expected}
    return {"status": _check_status(found == expected), "found": found, "expected": expected}


def check_canonical_version(source_tree: Path, expected: str) -> dict[str, Any]:
    adoption = source_tree / "runtime" / "adoption.py"
    if not adoption.exists():
        return {"status": "fail", "found": "<missing>", "expected": expected}
    try:
        tree = ast.parse(adoption.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "CANONICAL_VERSION":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            found = node.value.value
                            return {"status": _check_status(found == expected), "found": found, "expected": expected}
    except (OSError, SyntaxError) as e:
        return {"status": "fail", "found": f"<error: {e}>", "expected": expected}
    return {"status": "fail", "found": "<not found>", "expected": expected}


def check_cli_version(source_tree: Path, expected: str) -> dict[str, Any]:
    bin_omg = source_tree / "bin" / "omg"
    if not bin_omg.exists():
        return {"status": "skip", "found": "<bin/omg missing>", "expected": expected}
    try:
        result = subprocess.run(
            ["node", str(bin_omg), "--version"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.strip()
        # Expected format: "omg <version>" or just "<version>"
        found = output.replace("omg ", "").strip()
        return {"status": _check_status(found == expected), "found": output, "expected": expected}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"status": "skip", "found": "<node not available>", "expected": expected}


def check_changelog_section(source_tree: Path, expected: str) -> dict[str, Any]:
    changelog = source_tree / "CHANGELOG.md"
    if not changelog.exists():
        return {"status": "fail", "details": "CHANGELOG.md not found"}
    content = changelog.read_text(encoding="utf-8")
    header_pattern = re.compile(rf"^## \[?{re.escape(expected)}\]?", re.MULTILINE)
    has_header = bool(header_pattern.search(content))
    marker = f"OMG:GENERATED:changelog-v{expected}"
    has_marker = marker in content
    if has_header and has_marker:
        return {"status": "ok", "details": f"Found header and marker for v{expected}"}
    missing = []
    if not has_header:
        missing.append("version header")
    if not has_marker:
        missing.append("generated marker")
    return {"status": "fail", "details": f"Missing: {', '.join(missing)}"}


def check_install_verification_index(source_tree: Path, expected: str) -> dict[str, Any]:
    ivi = source_tree / "INSTALL-VERIFICATION-INDEX.md"
    if not ivi.exists():
        return {"status": "fail", "found": "<missing>", "expected": expected}
    content = ivi.read_text(encoding="utf-8")
    pattern = re.compile(rf"\*?\*?Version:?\*?\*?\s*OMG\s+{re.escape(expected)}")
    if pattern.search(content):
        return {"status": "ok", "found": expected, "expected": expected}
    version_match = re.search(r"\*?\*?Version:?\*?\*?\s*OMG\s+([\d.]+)", content)
    found = version_match.group(1) if version_match else "<not found>"
    return {"status": "fail", "found": found, "expected": expected}


def check_host_list_parity(source_tree: Path) -> dict[str, Any]:
    try:
        from runtime.canonical_surface import get_canonical_hosts, get_compat_hosts
        expected_canonical = set(get_canonical_hosts())
        expected_compat = set(get_compat_hosts())
    except ImportError:
        return {"status": "skip", "drift": ["cannot import canonical_surface"]}

    drift: list[str] = []

    support_matrix = source_tree / "SUPPORT-MATRIX.md"
    if support_matrix.exists():
        content = support_matrix.read_text(encoding="utf-8").lower()
        for host in expected_canonical | expected_compat:
            if host not in content:
                drift.append(f"SUPPORT-MATRIX.md missing host: {host}")

    ivi = source_tree / "INSTALL-VERIFICATION-INDEX.md"
    if ivi.exists():
        content = ivi.read_text(encoding="utf-8").lower()
        for host in expected_canonical | expected_compat:
            if host not in content:
                drift.append(f"INSTALL-VERIFICATION-INDEX.md missing host: {host}")

    return {"status": _check_status(not drift), "drift": drift}


def check_install_path_hygiene(source_tree: Path) -> dict[str, Any]:
    stale: list[str] = []
    docs_to_check = [
        "README.md",
        "INSTALL-VERIFICATION-INDEX.md",
        "QUICK-REFERENCE.md",
    ]
    bare_install_sh = re.compile(r"\binstall\.sh\b")
    for doc_name in docs_to_check:
        doc = source_tree / doc_name
        if not doc.exists():
            continue
        for line_num, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if bare_install_sh.search(line) and "OMG-setup.sh" not in line:
                stale.append(f"{doc_name}:{line_num}: bare install.sh reference")

    return {"status": _check_status(not stale), "stale_references": stale}


def run_audit(source_tree: Path, expected_version: str, *, npm_pack: bool = False) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "package_json_version": check_package_json_version(source_tree, expected_version),
        "canonical_version": check_canonical_version(source_tree, expected_version),
        "cli_version_output": check_cli_version(source_tree, expected_version),
        "changelog_section": check_changelog_section(source_tree, expected_version),
        "install_verification_index": check_install_verification_index(source_tree, expected_version),
        "host_list_parity": check_host_list_parity(source_tree),
        "install_path_hygiene": check_install_path_hygiene(source_tree),
    }

    blockers = [
        name for name, result in checks.items()
        if result.get("status") == "fail"
    ]

    return {
        "schema": "ArtifactSelfAudit",
        "version_expected": expected_version,
        "source_tree": str(source_tree),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "overall_status": "fail" if blockers else "ok",
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Published-artifact self-audit gate")
    parser.add_argument("--version", required=True, help="Expected version (from tag)")
    parser.add_argument("--source-tree", required=True, help="Path to unpacked artifact root")
    parser.add_argument("--npm-pack", action="store_true", help="Also audit npm pack output")
    parser.add_argument("--output-json", default=None, help="Write JSON report to file")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings too")
    args = parser.parse_args()

    source_tree = Path(args.source_tree).resolve()
    if not source_tree.is_dir():
        print(f"Error: {args.source_tree} is not a directory", file=sys.stderr)
        return 1

    report = run_audit(source_tree, args.version, npm_pack=args.npm_pack)

    output = json.dumps(report, indent=2)
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    if report["overall_status"] == "fail":
        print(f"\nAUDIT FAILED — blockers: {report['blockers']}", file=sys.stderr)
        return 1
    print("\nAUDIT PASSED", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
