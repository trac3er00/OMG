"""RalphBridge — state file coordination between parallel dispatch and Ralph autonomous loop.

Ralph operates via .omg/state/ralph-loop.json.
This bridge reads/writes to that file to coordinate WITHOUT modifying stop_dispatcher.py.
"""
from __future__ import annotations
import os
import sys
import json
import time
from typing import Any, Callable

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))


def _get_project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _get_atomic_json_write() -> Callable[..., Any] | None:
    """Lazy-import atomic_json_write from hooks/_common.py."""
    hooks_dir = os.path.join(_PROJECT_ROOT, "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import atomic_json_write  # type: ignore[import-not-found]
        return atomic_json_write  # type: ignore[no-any-return]
    except (ImportError, Exception):
        return None


def _atomic_write(path: str, data: dict[str, Any]) -> bool:
    """Write JSON atomically. Falls back to direct write if atomic_json_write unavailable."""
    write_fn = _get_atomic_json_write()
    if write_fn is not None:
        try:
            write_fn(path, data)
            return True
        except Exception:
            pass
    # Fallback: direct write with temp file swap
    import tempfile
    dirpath = os.path.dirname(path)
    os.makedirs(dirpath, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=dirpath, delete=False, suffix=".tmp") as f:
            json.dump(data, f, indent=2)
            tmp_path = f.name
        os.replace(tmp_path, path)
        return True
    except Exception:
        return False


class RalphBridge:
    """Coordinates parallel dispatch results with Ralph's autonomous loop via state files.

    Works standalone when Ralph is not active (returns safe defaults on missing state).
    NEVER imports or modifies hooks/stop_dispatcher.py.
    """

    RALPH_STATE_FILE = "ralph-loop.json"
    PARALLEL_RESULTS_FILE = "parallel-dispatch-results.json"

    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir or _get_project_dir()
        self._state_dir = os.path.join(self.project_dir, ".omg", "state")

    def _ralph_state_path(self) -> str:
        return os.path.join(self._state_dir, self.RALPH_STATE_FILE)

    def _results_path(self) -> str:
        return os.path.join(self._state_dir, self.PARALLEL_RESULTS_FILE)

    def _read_state_file(self, path: str) -> dict[str, Any] | None:
        """Read a JSON state file. Returns None if file doesn't exist or is malformed."""
        try:
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def is_ralph_active(self) -> bool:
        """Check if Ralph autonomous loop is currently active.

        Returns False if state file doesn't exist (standalone mode).
        """
        state = self._read_state_file(self._ralph_state_path())
        if state is None:
            return False
        return bool(state.get("active", False))

    def get_ralph_state(self) -> dict[str, Any]:
        """Get full Ralph loop state. Returns empty dict if not active."""
        state = self._read_state_file(self._ralph_state_path())
        return state or {}

    def write_results(self, results: list[dict[str, Any]]) -> bool:
        """Write parallel dispatch results to state file for Ralph consumption.

        Args:
            results: list of job result dicts
        Returns:
            True if write succeeded, False otherwise
        """
        data = {
            "schema_version": 1,
            "updated_at": time.time(),
            "results": results,
            "result_count": len(results),
        }
        return _atomic_write(self._results_path(), data)

    def signal_completion(self, job_id: str, status: str, artifacts: list[dict[str, Any]] | None = None) -> bool:
        """Signal job completion to Ralph via state file update.

        Args:
            job_id: The completed job ID
            status: 'completed', 'failed', or 'cancelled'
            artifacts: Optional list of artifact dicts from the job
        Returns:
            True if signal written, False otherwise
        """
        existing = self._read_state_file(self._results_path()) or {
            "schema_version": 1,
            "results": [],
            "result_count": 0,
        }

        # Upsert the job result
        results = existing.get("results", [])
        # Remove any existing entry for this job
        results = [r for r in results if r.get("job_id") != job_id]
        results.append({
            "job_id": job_id,
            "status": status,
            "artifacts": artifacts or [],
            "completed_at": time.time(),
        })

        existing["results"] = results
        existing["result_count"] = len(results)
        existing["updated_at"] = time.time()

        return _atomic_write(self._results_path(), existing)

    def read_results(self) -> list[dict[str, Any]]:
        """Read existing parallel dispatch results."""
        data = self._read_state_file(self._results_path())
        if data is None:
            return []
        return data.get("results", [])

    def clear_results(self) -> bool:
        """Clear the parallel dispatch results file."""
        return _atomic_write(self._results_path(), {
            "schema_version": 1,
            "updated_at": time.time(),
            "results": [],
            "result_count": 0,
        })
