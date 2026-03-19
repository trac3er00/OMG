#!/usr/bin/env python3
"""Published-artifact self-audit gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from runtime.release_artifact_audit import (
    check_canonical_version,
    check_changelog_section,
    check_cli_version,
    check_host_list_parity,
    check_install_path_hygiene,
    check_install_verification_index,
    check_package_json_version,
    run_source_tree_audit,
)

run_audit = run_source_tree_audit


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

    report = run_source_tree_audit(source_tree, args.version, npm_pack=args.npm_pack)

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
