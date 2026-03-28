"""
Cost Ledger Storage — JSONL persistence for token/cost tracking.

Provides append_cost_entry, read_cost_summary, and rotate_cost_ledger.
Follows the same fcntl locking + 5MB rotation pattern as tool-ledger.py.

Entry schema:
    {"ts": ISO8601, "tool": str, "tokens_in": int, "tokens_out": int,
     "cost_usd": float, "model": str, "session_id": str}

Pure stdlib — no external deps.
"""
import fcntl
import json
import os
import shutil
import sys
from typing import Any

# ── Constants ──
_LEDGER_SUBDIR = os.path.join(".omg", "state", "ledger")
_LEDGER_FILENAME = "cost-ledger.jsonl"
MAX_BYTES = 5 * 1024 * 1024  # 5MB rotation threshold


def _ledger_path(project_dir: str) -> str:
    """Return the absolute path to the cost ledger JSONL file."""
    return os.path.join(project_dir, _LEDGER_SUBDIR, _LEDGER_FILENAME)


def append_cost_entry(project_dir: str, entry: dict[str, object]) -> None:
    """Append a cost entry to the cost ledger JSONL file.

    Creates .omg/state/ledger/ if missing. Uses fcntl file locking
    with fallback to unlocked write (crash isolation invariant).

    Args:
        project_dir: Project root directory.
        entry: Dict with keys ts, tool, tokens_in, tokens_out,
               cost_usd, model, session_id.
    """
    ledger_dir = os.path.join(project_dir, _LEDGER_SUBDIR)
    os.makedirs(ledger_dir, exist_ok=True)

    path = _ledger_path(project_dir)
    line = json.dumps(entry, separators=(",", ":")) + "\n"

    try:
        fd = open(path, "a")
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(line)
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()
    except (ImportError, BlockingIOError):
        # Fallback: write without locking
        try:
            with open(path, "a") as f:
                f.write(line)
        except Exception:
            try:
                print(f"[omg:warn] failed to append cost ledger entry without lock fallback: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass
    except Exception:
        try:
            print(f"[omg:warn] failed to append cost ledger entry: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass


def read_cost_summary(project_dir: str, time_range=None) -> dict[str, Any]:
    """Read and aggregate cost entries from the ledger.

    Args:
        project_dir: Project root directory.
        time_range: Optional (start, end) ISO8601 strings for filtering.
                    Not yet implemented — reserved for future use.

    Returns:
        Dict with keys:
            total_tokens (int): Sum of tokens_in + tokens_out across all entries.
            total_cost_usd (float): Sum of cost_usd across all entries.
            by_tool (dict): {tool_name: {"tokens": int, "cost_usd": float, "count": int}}
            by_session (dict): {session_id: {"tokens": int, "cost_usd": float, "count": int}}
            entry_count (int): Number of valid entries processed.
    """
    empty = {
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "by_tool": {},
        "by_session": {},
        "entry_count": 0,
    }

    path = _ledger_path(project_dir)
    if not os.path.exists(path):
        return empty

    total_tokens = 0
    total_cost = 0.0
    by_tool: dict[str, dict[str, float | int]] = {}
    by_session: dict[str, dict[str, float | int]] = {}
    entry_count = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    # Skip malformed lines gracefully
                    continue

                tokens_in = entry.get("tokens_in", 0)
                tokens_out = entry.get("tokens_out", 0)
                cost_usd = entry.get("cost_usd", 0.0)
                tool = entry.get("tool", "unknown")
                session_id = entry.get("session_id", "unknown")
                line_tokens = tokens_in + tokens_out

                total_tokens += line_tokens
                total_cost += cost_usd
                entry_count += 1

                # Aggregate by tool
                if tool not in by_tool:
                    by_tool[tool] = {"tokens": 0, "cost_usd": 0.0, "count": 0}
                by_tool[tool]["tokens"] += line_tokens
                by_tool[tool]["cost_usd"] += cost_usd
                by_tool[tool]["count"] += 1

                # Aggregate by session
                if session_id not in by_session:
                    by_session[session_id] = {"tokens": 0, "cost_usd": 0.0, "count": 0}
                by_session[session_id]["tokens"] += line_tokens
                by_session[session_id]["cost_usd"] += cost_usd
                by_session[session_id]["count"] += 1

    except Exception:
        try:
            print(f"[omg:warn] failed while reading cost ledger summary: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass

    return {
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "by_tool": by_tool,
        "by_session": by_session,
        "entry_count": entry_count,
    }


def rotate_cost_ledger(project_dir: str) -> None:
    """Rotate cost ledger when it exceeds 5MB.

    Follows the same pattern as tool-ledger.py:
    - Size-only heuristic (avoids O(n) line-count scan)
    - Keeps only one archive with .1 suffix
    - Removes old archive before moving current file

    Args:
        project_dir: Project root directory.
    """
    path = _ledger_path(project_dir)

    try:
        if not os.path.exists(path):
            return

        size = os.path.getsize(path)
        if size <= MAX_BYTES:
            return

        archive = path + ".1"
        # Keep only one archive
        if os.path.exists(archive):
            try:
                os.remove(archive)
            except OSError:
                try:
                    print(f"[omg:warn] failed to remove prior cost ledger archive: {sys.exc_info()[1]}", file=sys.stderr)
                except Exception:
                    pass
        shutil.move(path, archive)
    except Exception:
        try:
            print(f"[omg:warn] failed to rotate cost ledger: {sys.exc_info()[1]}", file=sys.stderr)
        except Exception:
            pass
