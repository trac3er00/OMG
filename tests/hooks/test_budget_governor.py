"""Tests for budget governor PostToolUse hook (v2.0 — Task 7)."""
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

_COST_LEDGER_SPEC = importlib.util.spec_from_file_location("_cost_ledger", HOOKS_DIR / "_cost_ledger.py")
assert _COST_LEDGER_SPEC is not None and _COST_LEDGER_SPEC.loader is not None
_cost_ledger = importlib.util.module_from_spec(_COST_LEDGER_SPEC)
_COST_LEDGER_SPEC.loader.exec_module(_cost_ledger)
append_cost_entry = _cost_ledger.append_cost_entry


def _run_hook(payload: dict[str, Any], project_dir: Path, env: dict[str, str] | None = None):
    full_env = os.environ.copy()
    full_env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    if env:
        full_env.update(env)

    proc = subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(project_dir),
        env=full_env,
        check=False,
    )
    return proc


def _make_payload(
    tool_name: str = "Bash",
    tool_input: dict[str, Any] | None = None,
    tool_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_input": tool_input or {"command": "ls"},
        "tool_response": tool_response or {"stdout": "file.txt"},
    }


def _write_settings(project_dir: Path, data: dict[str, Any]):
    (project_dir / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def _base_settings() -> dict[str, Any]:
    return {
        "_omg": {
            "features": {"COST_TRACKING": False},
            "cost_budget": {
                "session_limit_usd": 5.0,
                "pricing": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
            },
        }
    }


def test_exits_silently_when_feature_disabled_in_settings():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _base_settings())

        proc = _run_hook(_make_payload(), project_dir, env={"OMG_COST_TRACKING_ENABLED": ""})

        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


def test_exits_silently_when_feature_disabled_by_env_override():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        settings = _base_settings()
        settings["_omg"]["features"]["COST_TRACKING"] = True
        _write_settings(project_dir, settings)

        proc = _run_hook(_make_payload(), project_dir, env={"OMG_COST_TRACKING_ENABLED": "0"})

        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


def test_outputs_budget_context_when_feature_enabled_by_env():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _base_settings())

        proc = _run_hook(_make_payload(), project_dir, env={"OMG_COST_TRACKING_ENABLED": "1"})

        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        context = output["additionalContext"]
        assert context.startswith("Budget:")
        assert "remaining" in context
        assert "tool calls" in context


def test_includes_spend_from_cost_ledger_summary():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        settings = _base_settings()
        settings["_omg"]["cost_budget"]["session_limit_usd"] = 2.0
        _write_settings(project_dir, settings)

        append_cost_entry(
            str(project_dir),
            {
                "ts": "2026-03-04T10:00:00Z",
                "tool": "Bash",
                "tokens_in": 120,
                "tokens_out": 80,
                "cost_usd": 0.57,
                "model": "claude-sonnet",
                "session_id": "sess-1",
            },
        )

        proc = _run_hook(_make_payload(), project_dir, env={"OMG_COST_TRACKING_ENABLED": "1"})
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "$" in context
        assert "of $2.00 used" in context


def test_uses_configurable_pricing_for_token_estimate():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        settings = _base_settings()
        settings["_omg"]["cost_budget"]["pricing"] = {"input_per_mtok": 10.0, "output_per_mtok": 30.0}
        _write_settings(project_dir, settings)

        payload = _make_payload(tool_input={"command": "printf 'hello world'"}, tool_response={"stdout": "ok"})
        proc = _run_hook(payload, project_dir, env={"OMG_COST_TRACKING_ENABLED": "1"})
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "Budget:" in context
        assert "$" in context


def test_always_exits_zero_on_invalid_json_input():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _base_settings())

        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
        env["OMG_COST_TRACKING_ENABLED"] = "1"

        proc = subprocess.run(
            ["python3", str(SCRIPT_PATH)],
            input="{not valid json",
            text=True,
            capture_output=True,
            cwd=str(project_dir),
            env=env,
            check=False,
        )

        assert proc.returncode == 0


def test_output_matches_budget_status_shape():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        settings = _base_settings()
        settings["_omg"]["cost_budget"]["session_limit_usd"] = 2.0
        _write_settings(project_dir, settings)

        proc = _run_hook(_make_payload(), project_dir, env={"OMG_COST_TRACKING_ENABLED": "1"})
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "Budget:" in context
        assert "remaining |" in context
        assert "used |" in context
        assert "tool calls" in context


def test_falls_back_to_default_budget_when_missing_config():
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, {"_omg": {"features": {"COST_TRACKING": False}}})

        proc = _run_hook(_make_payload(), project_dir, env={"OMG_COST_TRACKING_ENABLED": "1"})
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]
        assert "of $5.00 used" in context


# ── Session-scoping regression tests (Task 11) ──────────────────────


def _enabled_settings(limit_usd: float = 5.0) -> dict[str, Any]:
    return {
        "_omg": {
            "features": {"COST_TRACKING": True},
            "cost_budget": {
                "session_limit_usd": limit_usd,
                "pricing": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
            },
        }
    }


def test_session_scoping_does_not_bleed_across_sessions():
    """Session A's high spend must NOT trigger alerts when evaluating session B."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _enabled_settings(5.0))

        # Session A: $4.50 spent (90% of $5 limit — would trigger 50+80% thresholds)
        append_cost_entry(
            str(project_dir),
            {
                "ts": "2026-03-15T10:00:00Z",
                "tool": "Bash",
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_usd": 4.50,
                "model": "claude-sonnet",
                "session_id": "sess-A",
            },
        )

        # Session B: $0.30 spent (6% of $5 limit — well below any threshold)
        append_cost_entry(
            str(project_dir),
            {
                "ts": "2026-03-15T10:01:00Z",
                "tool": "Bash",
                "tokens_in": 50,
                "tokens_out": 25,
                "cost_usd": 0.30,
                "model": "claude-sonnet",
                "session_id": "sess-B",
            },
        )

        # Evaluate as session B — should see only session B's $0.30
        proc = _run_hook(
            _make_payload(),
            project_dir,
            env={"CLAUDE_SESSION_ID": "sess-B", "OMG_COST_TRACKING_ENABLED": "1"},
        )
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        context = output["additionalContext"]

        # Session B is at ~6%, NOT 96% — no threshold alerts should fire
        assert "@cost-warning" not in context
        assert "@cost-critical" not in context
        assert "@cost-limit" not in context

        # Budget context should NOT show session A's $4.50 contribution
        assert "$4" not in context


def test_session_scoping_uses_correct_session_cost():
    """Budget context reflects only the current session's cumulative spend."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _enabled_settings(10.0))

        # Session X: $8.00
        append_cost_entry(
            str(project_dir),
            {
                "ts": "2026-03-15T10:00:00Z",
                "tool": "Bash",
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_usd": 8.00,
                "model": "claude-sonnet",
                "session_id": "sess-X",
            },
        )

        # Session Y: $1.00
        append_cost_entry(
            str(project_dir),
            {
                "ts": "2026-03-15T10:01:00Z",
                "tool": "Bash",
                "tokens_in": 50,
                "tokens_out": 25,
                "cost_usd": 1.00,
                "model": "claude-sonnet",
                "session_id": "sess-Y",
            },
        )

        # Evaluate as session Y — should show ~$1.00, not $9.00
        proc = _run_hook(
            _make_payload(),
            project_dir,
            env={"CLAUDE_SESSION_ID": "sess-Y", "OMG_COST_TRACKING_ENABLED": "1"},
        )
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["additionalContext"]

        # Should show ~$1.xx of $10.00, not $9.xx of $10.00
        assert "$1." in context
        assert "$9" not in context


def test_budget_decision_includes_provenance_field():
    """Budget output includes a provenance field when session data is available."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _enabled_settings(5.0))

        # Add entry matching the session we'll query
        append_cost_entry(
            str(project_dir),
            {
                "ts": "2026-03-15T10:00:00Z",
                "tool": "Bash",
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_usd": 0.10,
                "model": "claude-sonnet",
                "session_id": "sess-prov",
            },
        )

        proc = _run_hook(
            _make_payload(),
            project_dir,
            env={"OMG_COST_TRACKING_ENABLED": "1", "CLAUDE_SESSION_ID": "sess-prov"},
        )
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert "provenance" in output
        assert output["provenance"] == "session"


def test_provenance_default_when_no_session_data():
    """Provenance is 'default' when session has no ledger entries."""
    with tempfile.TemporaryDirectory() as d:
        project_dir = Path(d)
        _write_settings(project_dir, _enabled_settings(5.0))

        proc = _run_hook(
            _make_payload(),
            project_dir,
            env={"OMG_COST_TRACKING_ENABLED": "1", "CLAUDE_SESSION_ID": "sess-unknown"},
        )
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert output.get("provenance") == "default"
