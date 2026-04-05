"""CLI entry point for bulk XOR→Fernet memory migration.

Usage:
    python3 -m runtime.memory_migrate [--store-path PATH] [--batch-size N] [--dry-run]
    npx omg memory migrate  (dispatches to this module)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime.memory_store import MemoryStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omg-memory-migrate",
        description="Migrate XOR-encrypted memory entries to Fernet",
    )
    parser.add_argument(
        "--store-path",
        default=str(Path.home() / ".omg" / "shared-memory" / "store.sqlite3"),
        help="Path to memory store (default: ~/.omg/shared-memory/store.sqlite3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Rows per commit batch (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report without writing changes",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report as JSON",
    )

    args = parser.parse_args(argv)
    store = MemoryStore(store_path=args.store_path)

    try:
        report = store.migrate_all(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    finally:
        store.close()

    if args.json_output:
        print(json.dumps(report, indent=2))
    else:
        mode = "DRY RUN" if report["dry_run"] else "APPLIED"
        print(f"Memory migration [{mode}]")
        print(f"  Total entries:    {report['total']}")
        print(f"  Already Fernet:   {report['already_fernet']}")
        print(f"  Migrated (XOR→F): {report['migrated']}")
        print(f"  Corrupted/skip:   {report['corrupted']}")
        if report["errors"]:
            print("\nErrors:")
            for err in report["errors"]:
                print(f"  - {err}")

    return 1 if report["corrupted"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
