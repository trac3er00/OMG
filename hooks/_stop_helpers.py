"""Extracted helper functions for stop_dispatcher.py.

These utilities were extracted from stop_dispatcher.py to reduce its size
and improve testability. The main dispatcher imports them as needed.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any


def read_checklist_progress(checklist_path: str) -> tuple[int, int, str | None]:
    """Read checklist progress: (done, total, first_pending_text).

    Returns (0, 0, None) if file doesn't exist or can't be parsed.
    """
    if not os.path.exists(checklist_path):
        return 0, 0, None
    try:
        with open(checklist_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        total = sum(1 for l in lines if re.search(r'^\s*-\s*\[[ x!]\]', l))
        done = sum(1 for l in lines if re.search(r'^\s*-\s*\[x\]', l, re.IGNORECASE))
        first_pending = None
        for l in lines:
            if re.search(r'^\s*-\s*\[ \]', l):
                first_pending = l.strip().lstrip("- [ ]").strip()
                break
        return done, total, first_pending
    except OSError:
        return 0, 0, None


def count_blocked_items(checklist_path: str) -> int:
    """Count items marked as blocked [!] in the checklist."""
    if not os.path.exists(checklist_path):
        return 0
    try:
        with open(checklist_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for l in f if re.search(r'^\s*-\s*\[!\]', l))
    except OSError:
        return 0


def parse_diff_stat(diff_output: str) -> tuple[int, int]:
    """Parse git diff --stat output into (files_changed, lines_changed).

    Returns (0, 0) on empty or unparseable input.
    """
    if not diff_output or not diff_output.strip():
        return 0, 0
    lines = diff_output.strip().split("\n")
    summary_line = lines[-1] if lines else ""
    files = 0
    total_lines = 0
    # Parse "N files changed, M insertions(+), P deletions(-)"
    files_match = re.search(r'(\d+)\s+files?\s+changed', summary_line)
    if files_match:
        files = int(files_match.group(1))
    ins_match = re.search(r'(\d+)\s+insertions?', summary_line)
    del_match = re.search(r'(\d+)\s+deletions?', summary_line)
    if ins_match:
        total_lines += int(ins_match.group(1))
    if del_match:
        total_lines += int(del_match.group(1))
    return files, total_lines


def is_test_file(path: str) -> bool:
    """Return True if the path looks like a test file."""
    basename = os.path.basename(path).lower()
    return (
        basename.startswith("test_")
        or basename.endswith("_test.py")
        or basename.endswith(".test.ts")
        or basename.endswith(".test.js")
        or basename.endswith(".test.tsx")
        or basename.endswith(".test.jsx")
        or basename.endswith(".spec.ts")
        or basename.endswith(".spec.js")
        or "/tests/" in path
        or "/__tests__/" in path
    )


def is_source_file(path: str) -> bool:
    """Return True if the path looks like a source code file (not config/docs)."""
    ext = os.path.splitext(path)[1].lower()
    return ext in {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".rb", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt",
    }


def format_evidence_summary(
    verified: list[str],
    unverified: list[str],
    assumptions: list[str],
) -> str:
    """Format the evidence summary for stop-gate reporting."""
    parts = []
    if verified:
        parts.append("Verified: " + "; ".join(verified))
    if unverified:
        parts.append("Unverified: " + "; ".join(unverified))
    if assumptions:
        parts.append("Assumptions: " + "; ".join(assumptions))
    return " | ".join(parts) if parts else "No evidence collected"
