"""State file rotation — auto-archive files older than 30 days.

Scans .omg/state/ledger/ for JSONL and JSON files, moves those
older than the configured max age to .omg/state/archive/.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


DEFAULT_MAX_AGE_DAYS = 30
ARCHIVE_SUBDIR = "archive"
LEDGER_SUBDIR = os.path.join(".omg", "state", "ledger")


def rotate_state_files(
    project_dir: str,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Rotate old state files to archive directory.

    Returns dict with 'archived' and 'skipped' file lists.
    """
    ledger_dir = os.path.join(project_dir, LEDGER_SUBDIR)
    archive_dir = os.path.join(project_dir, ".omg", "state", ARCHIVE_SUBDIR)
    cutoff = time.time() - (max_age_days * 86400)

    result: dict[str, list[str]] = {"archived": [], "skipped": []}

    if not os.path.isdir(ledger_dir):
        return result

    for fname in os.listdir(ledger_dir):
        fpath = os.path.join(ledger_dir, fname)
        if not os.path.isfile(fpath):
            continue
        if not fname.endswith((".jsonl", ".json", ".log")):
            continue
        # Skip lock files and active trackers
        if fname.endswith(".lock") or fname.startswith("."):
            continue

        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            continue

        if mtime < cutoff:
            if not dry_run:
                os.makedirs(archive_dir, exist_ok=True)
                dest = os.path.join(archive_dir, fname)
                # Append timestamp to avoid overwrites
                if os.path.exists(dest):
                    base, ext = os.path.splitext(fname)
                    dest = os.path.join(archive_dir, f"{base}_{int(mtime)}{ext}")
                shutil.move(fpath, dest)
            result["archived"].append(fname)
        else:
            result["skipped"].append(fname)

    return result
