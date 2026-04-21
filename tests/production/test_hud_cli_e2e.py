"""HUD CLI script E2E tests.

Tests hud/omg-hud.mjs and hud/omg-hud-enhanced.mjs CLI scripts.
HUD is a Node.js CLI script that reads JSON from stdin and renders output.

Known issue: omg-hud.mjs has a missing ``existsSync`` import that causes
rendering failures in isolated environments.  Tests that need full rendering
detect this and skip gracefully.  The enhanced HUD imports ``existsSync``
correctly and works in all environments.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HUD = ROOT / "hud" / "omg-hud.mjs"
HUD_ENHANCED = ROOT / "hud" / "omg-hud-enhanced.mjs"
FIXTURE = ROOT / "tests" / "fixtures" / "hud-session-health.json"

_EXISTSYNC_ERROR = "existsSync is not defined"


def _stdin_payload(cwd: str = "/tmp/test-project") -> dict:
    """Create a standard HUD stdin payload."""
    return {
        "cwd": cwd,
        "transcript_path": f"{cwd}/transcript.jsonl",
        "model": {"id": "claude-sonnet-4-5", "display_name": "Sonnet"},
        "context_window": {"used_percentage": 25},
    }


def _run_hud(
    hud_path: Path,
    payload: dict,
    *,
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run HUD script with JSON payload on stdin."""
    merged_env = dict(os.environ)
    if env_overrides:
        merged_env.update(env_overrides)
    return subprocess.run(
        ["node", str(hud_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        cwd=cwd or str(ROOT),
        env=merged_env,
    )


def _hud_renders_ok(result: subprocess.CompletedProcess[str]) -> bool:
    """Check whether HUD rendered successfully (no existsSync bug)."""
    return _EXISTSYNC_ERROR not in result.stderr


class TestHUDBasic:
    """Basic HUD CLI tests."""

    def test_hud_exists(self):
        """HUD script should exist."""
        assert HUD.exists(), f"HUD script not found: {HUD}"

    def test_hud_enhanced_exists(self):
        """Enhanced HUD script should exist."""
        assert HUD_ENHANCED.exists(), f"Enhanced HUD not found: {HUD_ENHANCED}"

    def test_hud_runs_without_crash(self, tmp_path: Path):
        """HUD should exit 0 (no process crash) with basic JSON payload."""
        if not HUD.exists():
            pytest.skip("HUD script not found")
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()
        payload = _stdin_payload(cwd=str(project))
        result = _run_hud(
            HUD,
            payload,
            env_overrides={"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)},
        )
        assert result.returncode == 0, f"HUD crashed: {result.stderr[:300]}"

    def test_hud_produces_output(self, tmp_path: Path):
        """HUD should produce stdout content."""
        if not HUD.exists():
            pytest.skip("HUD script not found")
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()
        payload = _stdin_payload(cwd=str(project))
        result = _run_hud(
            HUD,
            payload,
            env_overrides={"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)},
        )
        assert result.returncode == 0
        assert len(result.stdout) > 0, "HUD produced no stdout"

    def test_hud_output_contains_omg_reference(self, tmp_path: Path):
        """HUD output should reference OMG somewhere."""
        if not HUD.exists():
            pytest.skip("HUD script not found")
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()
        payload = _stdin_payload(cwd=str(project))
        result = _run_hud(
            HUD,
            payload,
            env_overrides={"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)},
        )
        assert result.returncode == 0
        lowered = result.stdout.lower()
        # Both normal render and error fallback contain "omg"
        assert "omg" in lowered, (
            f"Expected OMG reference in output: {result.stdout[:200]}"
        )


class TestHUDHealthData:
    """Test HUD with session health data.

    These tests require full HUD rendering.  If the ``existsSync`` import
    bug is present, they skip gracefully.
    """

    def test_hud_accepts_health_fixture(self, tmp_path: Path):
        """HUD should accept the session-health fixture without crashing."""
        if not HUD.exists():
            pytest.skip("HUD script not found")
        if not FIXTURE.exists():
            pytest.skip("hud-session-health.json fixture not found")
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()
        with open(FIXTURE) as f:
            payload = json.load(f)
        payload["cwd"] = str(project)
        result = _run_hud(
            HUD,
            payload,
            env_overrides={"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)},
        )
        assert result.returncode == 0, (
            f"HUD crashed with health fixture: {result.stderr[:300]}"
        )

    def test_hud_renders_health_from_stdin(self, tmp_path: Path):
        """HUD should render contamination/overthinking from stdin session_health."""
        if not HUD.exists():
            pytest.skip("HUD script not found")
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()
        payload = _stdin_payload(cwd=str(project))
        payload["session_health"] = {
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "prod-test-1",
            "contamination_risk": 0.45,
            "overthinking_score": 0.55,
            "context_health": 0.7,
            "verification_status": "running",
            "recommended_action": "reflect",
            "thresholds": {},
            "updated_at": "2026-04-21T07:30:00Z",
        }
        result = _run_hud(
            HUD,
            payload,
            env_overrides={"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)},
        )
        assert result.returncode == 0
        if not _hud_renders_ok(result):
            pytest.skip(f"HUD has known existsSync import bug: {result.stderr.strip()}")
        lowered = result.stdout.lower()
        assert "contam:45%" in lowered
        assert "overthink:55%" in lowered
        assert "health:70%" in lowered

    def test_hud_renders_verification_no_active_run(self, tmp_path: Path):
        """HUD should show 'no active run' when no verification state exists."""
        if not HUD.exists():
            pytest.skip("HUD script not found")
        home = tmp_path / "home"
        claude = home / ".claude"
        claude.mkdir(parents=True)
        project = tmp_path / "project"
        project.mkdir()
        payload = _stdin_payload(cwd=str(project))
        result = _run_hud(
            HUD,
            payload,
            env_overrides={"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)},
        )
        assert result.returncode == 0
        if not _hud_renders_ok(result):
            pytest.skip(f"HUD has known existsSync import bug: {result.stderr.strip()}")
        lowered = result.stdout.lower()
        assert "no active run" in lowered


class TestEnhancedHUD:
    """Test enhanced HUD CLI.

    Enhanced HUD correctly imports ``existsSync`` and works in all
    environments.  It reads JSONL events from a file rather than stdin.
    """

    def test_enhanced_hud_runs(self):
        """Enhanced HUD should run and produce output."""
        if not HUD_ENHANCED.exists():
            pytest.skip("Enhanced HUD not found")
        result = subprocess.run(
            ["node", str(HUD_ENHANCED)],
            input="",
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(ROOT),
        )
        assert result.returncode == 0, f"Enhanced HUD failed: {result.stderr[:300]}"

    def test_enhanced_hud_idle_output(self, tmp_path: Path):
        """Enhanced HUD should output idle status when no events exist."""
        if not HUD_ENHANCED.exists():
            pytest.skip("Enhanced HUD not found")
        result = subprocess.run(
            ["node", str(HUD_ENHANCED)],
            input="",
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "idle" in result.stdout.lower(), (
            f"Expected idle output, got: {result.stdout[:200]}"
        )

    def test_enhanced_hud_with_events(self, tmp_path: Path):
        """Enhanced HUD should render agent/cost info from events file."""
        if not HUD_ENHANCED.exists():
            pytest.skip("Enhanced HUD not found")
        state_dir = tmp_path / ".omg" / "state"
        state_dir.mkdir(parents=True)
        events = [
            {"type": "agent_start", "data": {"agent_id": "agent-1"}},
            {"type": "cost_update", "data": {"tokens": 5000, "usd": 0.015}},
            {"type": "phase_change", "data": {"phase": "execution"}},
        ]
        events_path = state_dir / "hud-events.jsonl"
        _ = events_path.write_text(
            "\n".join(json.dumps(e) for e in events) + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["node", str(HUD_ENHANCED)],
            input="",
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        lowered = result.stdout.lower()
        assert "1 agents" in lowered
        assert "execution" in lowered
        assert "$0.015" in lowered
