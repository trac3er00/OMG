"""Tests for threshold alerting system in budget_governor (Task 8)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "hooks"
SCRIPT_PATH = HOOKS_DIR / "budget_governor.py"

sys.path.insert(0, str(HOOKS_DIR))

_COST_LEDGER_SPEC = importlib.util.spec_from_file_location(
    "_cost_ledger", HOOKS_DIR / "_cost_ledger.py"
)
assert _COST_LEDGER_SPEC is not None and _COST_LEDGER_SPEC.loader is not None
_cost_ledger = importlib.util.module_from_spec(_COST_LEDGER_SPEC)
_COST_LEDGER_SPEC.loader.exec_module(_cost_ledger)
append_cost_entry = _cost_ledger.append_cost_entry


# ── helpers ──────────────────────────────────────────────────────────

def _run_hook(
    payload: dict[str, Any],
    project_dir: Path,
    env: dict[str, str] | None = None,
):
    full_env = os.environ.copy()
    full_env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    full_env["OMG_COST_TRACKING_ENABLED"] = "1"
    if env:
        full_env.update(env)

    return subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(project_dir),
        env=full_env,
        check=False,
    )


def _make_payload(
    tool_name: str = "Bash",
    tool_input: dict[str, Any] | None = None,
    tool_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_input": tool_input or {"command": "ls"},
        "tool_response": tool_response or {"stdout": "ok"},
    }


def _write_settings(project_dir: Path, data: dict[str, Any]):
    (project_dir / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def _settings_with_limit(
    limit_usd: float = 5.0,
    thresholds: list[int] | None = None,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "_omg": {
            "features": {"COST_TRACKING": True},
            "cost_budget": {
                "session_limit_usd": limit_usd,
                "pricing": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
            },
        }
    }
    if thresholds is not None:
        cfg["_omg"]["cost_budget"]["thresholds"] = thresholds
    return cfg


def _add_cost(project_dir: Path, cost_usd: float, session_id: str = "test-sess"):
    append_cost_entry(
        str(project_dir),
        {
            "ts": "2026-03-04T10:00:00Z",
            "tool": "Bash",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": cost_usd,
            "model": "claude-sonnet",
            "session_id": session_id,
        },
    )


def _state_path(project_dir: Path) -> Path:
    return project_dir / ".omg" / "state" / ".cost-threshold-state.json"


def _read_state(project_dir: Path) -> dict[str, Any]:
    p = _state_path(project_dir)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ── tests ────────────────────────────────────────────────────────────


def test_50pct_threshold_injects_warning():
    """At ≥50% budget usage, additionalContext includes @cost-warning."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0))
        _add_cost(project_dir, 5.0)  # 50% of $10

        proc = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-50"}
        )

        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "@cost-warning: 50% budget used" in context


def test_80pct_threshold_injects_critical():
    """At ≥80% budget usage, additionalContext includes @cost-critical with efficiency guidance."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0))
        _add_cost(project_dir, 8.0)  # 80% of $10

        proc = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-80"}
        )

        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "@cost-critical: 80% budget used" in context
        assert "Be efficient" in context


def test_95pct_threshold_injects_limit():
    """At ≥95% budget usage, additionalContext includes @cost-limit with stop directive."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0))
        _add_cost(project_dir, 9.5)  # 95% of $10

        proc = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-95"}
        )

        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "@cost-limit: 95% budget used" in context
        assert "Complete current task and stop" in context


def test_threshold_fires_only_once_per_session():
    """Second invocation at same threshold does NOT re-inject the alert."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0))
        _add_cost(project_dir, 5.0)  # 50%

        # First run — fires 50% alert
        proc1 = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-once"}
        )
        assert proc1.returncode == 0
        ctx1 = json.loads(proc1.stdout)["additionalContext"]
        assert "@cost-warning: 50% budget used" in ctx1

        # Second run — same session, should NOT contain 50% alert
        proc2 = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-once"}
        )
        assert proc2.returncode == 0
        ctx2 = json.loads(proc2.stdout)["additionalContext"]
        assert "@cost-warning" not in ctx2


def test_state_file_tracks_fired_thresholds():
    """State file records session_id and all crossed thresholds."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0))
        _add_cost(project_dir, 8.5)  # crosses 50% and 80%

        _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-state"}
        )

        state = _read_state(project_dir)
        assert state.get("session_id") == "s-state"
        assert 50 in state.get("fired", [])
        assert 80 in state.get("fired", [])


def test_new_session_resets_threshold_state():
    """Different session_id resets fired thresholds — alert fires again."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0))
        _add_cost(project_dir, 5.0)  # 50%

        # First session fires 50%
        _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-old"}
        )
        state1 = _read_state(project_dir)
        assert 50 in state1.get("fired", [])

        # New session — should fire 50% again
        proc = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-new"}
        )
        ctx = json.loads(proc.stdout)["additionalContext"]
        assert "@cost-warning: 50% budget used" in ctx
        state2 = _read_state(project_dir)
        assert state2.get("session_id") == "s-new"


def test_custom_thresholds_from_settings():
    """Thresholds configurable via _omg.cost_budget.thresholds in settings.json."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0, thresholds=[30, 70]))
        _add_cost(project_dir, 3.5)  # 35% — past 30% but not 70%

        proc = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-custom"}
        )

        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "@cost-warning: 30% budget used" in context
        # 70% threshold should NOT fire at 35%
        assert "70%" not in context


def test_below_threshold_no_alert():
    """Below any threshold, no @cost- alert injected."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _settings_with_limit(10.0))
        _add_cost(project_dir, 2.0)  # 20% — well below 50%

        proc = _run_hook(
            _make_payload(), project_dir, env={"CLAUDE_SESSION_ID": "s-low"}
        )

        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "@cost-" not in context
