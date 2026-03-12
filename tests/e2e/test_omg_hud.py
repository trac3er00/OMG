"""Tests for OMG HUD compatibility behavior."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from datetime import UTC, datetime, timedelta
from typing import cast

from runtime.adoption import CANONICAL_VERSION


ROOT = Path(__file__).resolve().parents[2]
HUD = ROOT / "hud" / "omg-hud.mjs"


def _run_hud_script(script: Path, payload: dict[str, object], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    merged_env.update(env)
    return subprocess.run(
        ["node", str(script)],
        input=json.dumps(payload),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def _run_hud(payload: dict[str, object], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run_hud_script(HUD, payload, env)


def _stdin_payload(cwd: Path) -> dict[str, object]:
    return cast(
        dict[str, object],
        {
        "cwd": str(cwd),
        "transcript_path": str(cwd / "transcript.jsonl"),
        "model": {"id": "claude-sonnet-4-5", "display_name": "Sonnet"},
        "context_window": {"used_percentage": 25},
        },
    )


def test_hud_honors_legacy_omc_hud_toggle_for_model(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    _ = (claude / "settings.json").write_text(
        json.dumps({"omcHud": {"elements": {"model": False}}}),
        encoding="utf-8",
    )

    project = tmp_path / "project"
    project.mkdir(parents=True)
    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert "sonnet" not in out.stdout.lower()


def test_hud_honors_legacy_omc_hud_toggle_for_label(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    _ = (claude / "settings.json").write_text(
        json.dumps({"omcHud": {"elements": {"omcLabel": False}}}),
        encoding="utf-8",
    )

    project = tmp_path / "project"
    project.mkdir(parents=True)
    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert "[omg#" not in out.stdout.lower()


def test_copied_hud_reads_version_from_installed_settings(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    hud_dir = claude / "hud"
    hud_dir.mkdir(parents=True)
    copied_hud = hud_dir / "omg-hud.mjs"
    copied_hud.write_text(HUD.read_text(encoding="utf-8"), encoding="utf-8")
    _ = (claude / "settings.json").write_text(
        json.dumps({"_omg": {"_version": CANONICAL_VERSION}}),
        encoding="utf-8",
    )

    project = tmp_path / "project"
    project.mkdir(parents=True)
    payload = _stdin_payload(project)
    out = _run_hud_script(copied_hud, payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert f"[omg#{CANONICAL_VERSION}]".lower() in out.stdout.lower()


def test_copied_hud_static_fallback_matches_canonical_version(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    hud_dir = claude / "hud"
    hud_dir.mkdir(parents=True)
    copied_hud = hud_dir / "omg-hud.mjs"
    copied_hud.write_text(HUD.read_text(encoding="utf-8"), encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir(parents=True)
    payload = _stdin_payload(project)

    out = _run_hud_script(copied_hud, payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert f"[omg#{CANONICAL_VERSION}]".lower() in out.stdout.lower()


def test_hud_defaults_follow_omc_baseline(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    ledger = project / ".omg" / "state" / "ledger"
    ledger.mkdir(parents=True)
    _ = (ledger / "tool-ledger.jsonl").write_text("x" * 800, encoding="utf-8")

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    # Legacy baseline defaults: model hidden, call counts shown.
    assert "sonnet" not in out.stdout.lower()
    assert "dir:" in out.stdout.lower()
    assert "agents:" in out.stdout.lower()
    assert "hooks:" not in out.stdout.lower()


def test_hud_reads_legacy_omc_hud_config_file(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    (claude / ".omc").mkdir(parents=True)
    _ = (claude / ".omc" / "hud-config.json").write_text(
        json.dumps({"elements": {"model": True, "omcLabel": False}}),
        encoding="utf-8",
    )

    project = tmp_path / "project"
    project.mkdir(parents=True)
    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert "sonnet" in out.stdout.lower()
    assert "[omg#" not in out.stdout.lower()


def test_hud_applies_legacy_preset_overrides(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    _ = (claude / "settings.json").write_text(
        json.dumps({"omcHud": {"preset": "minimal"}}),
        encoding="utf-8",
    )

    project = tmp_path / "project"
    state = project / ".omg" / "state"
    state.mkdir(parents=True)
    _ = (state / "hud-state.json").write_text(
        json.dumps({"lastPromptTimestamp": "2026-02-27T21:13:00.000Z"}),
        encoding="utf-8",
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert "prompt:" not in out.stdout.lower()
    assert "ctx:" not in out.stdout.lower()


def test_hud_supports_standard_preset_name(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    _ = (claude / "settings.json").write_text(
        json.dumps({"omcHud": {"preset": "standard"}}),
        encoding="utf-8",
    )

    project = tmp_path / "project"
    project.mkdir(parents=True)
    payload = _stdin_payload(project)

    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert "context:[" in out.stdout.lower()


def test_hud_treats_focused_as_alias_of_standard(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    project.mkdir(parents=True)
    payload = _stdin_payload(project)

    _ = (claude / "settings.json").write_text(
        json.dumps({"omcHud": {"preset": "standard"}}),
        encoding="utf-8",
    )
    standard_out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})

    _ = (claude / "settings.json").write_text(
        json.dumps({"omcHud": {"preset": "focused"}}),
        encoding="utf-8",
    )
    focused_out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})

    assert standard_out.returncode == 0
    assert focused_out.returncode == 0
    assert focused_out.stdout == standard_out.stdout


def test_hud_shows_session_used_tokens_from_stdin_usage(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    project.mkdir(parents=True)

    payload = _stdin_payload(project)
    payload["context_window"] = {
        "used_percentage": 25,
        "current_usage": {
            "input_tokens": 1200,
            "output_tokens": 800,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 2500,
        },
    }

    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "session:" in lowered


def test_hud_shows_weekly_used_tokens_from_stats_cache(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    stats = {
        "dailyModelTokens": [
            {"date": today.isoformat(), "tokensByModel": {"claude-opus-4-6": 12345}},
            {"date": yesterday.isoformat(), "tokensByModel": {"claude-opus-4-6": 2000}},
        ]
    }
    _ = (claude / "stats-cache.json").write_text(json.dumps(stats), encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir(parents=True)

    payload = _stdin_payload(project)
    payload["context_window"] = {
        "used_percentage": 25,
        "current_usage": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 250,
            "cache_read_input_tokens": 250,
        },
    }

    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "session:" in lowered
    assert "daily:" in lowered
    assert "weekly:" in lowered


def test_hud_shows_daily_and_weekly_usage_even_when_rate_limits_disabled(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    _ = (claude / "settings.json").write_text(
        json.dumps({"omcHud": {"preset": "minimal"}}),
        encoding="utf-8",
    )

    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    stats = {
        "dailyModelTokens": [
            {"date": today.isoformat(), "tokensByModel": {"claude-opus-4-6": 5000}},
            {"date": yesterday.isoformat(), "tokensByModel": {"claude-opus-4-6": 2500}},
        ]
    }
    _ = (claude / "stats-cache.json").write_text(json.dumps(stats), encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir(parents=True)

    payload = _stdin_payload(project)
    payload["context_window"] = {
        "used_percentage": 25,
        "current_usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 25,
            "cache_read_input_tokens": 25,
        },
    }

    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "session:" in lowered
    assert "daily:" in lowered
    assert "weekly:" in lowered


def test_hud_falls_back_to_session_tokens_for_daily_and_weekly_when_no_stats(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    project.mkdir(parents=True)

    payload = _stdin_payload(project)
    payload["context_window"] = {
        "used_percentage": 25,
        "current_usage": {
            "input_tokens": 1200,
            "output_tokens": 800,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 2500,
        },
    }

    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "session:5.0k" in lowered
    assert "daily:" not in lowered  # No stats cache, so no daily/weekly
    assert "weekly:" not in lowered


def test_hud_renders_verification_status_when_state_present(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    state_dir = project / ".omg" / "state"
    state_dir.mkdir(parents=True)

    verification_state = {
        "schema": "BackgroundVerificationState",
        "schema_version": 2,
        "run_id": "test-run-1",
        "status": "ok",
        "blockers": [],
        "evidence_links": [".omg/evidence/test.json"],
        "progress": {"total": 5, "completed": 5},
        "updated_at": "2026-03-01T12:00:00Z",
    }
    (state_dir / "background-verification.json").write_text(
        json.dumps(verification_state), encoding="utf-8"
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "verification ok" in lowered


def test_hud_renders_fallback_when_verification_state_missing(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    project.mkdir(parents=True)

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "verification: unknown" in lowered


def test_hud_renders_blocker_count_when_blockers_present(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    state_dir = project / ".omg" / "state"
    state_dir.mkdir(parents=True)

    verification_state = {
        "schema": "BackgroundVerificationState",
        "schema_version": 2,
        "run_id": "test-run-2",
        "status": "blocked",
        "blockers": ["lint failure", "test timeout"],
        "evidence_links": [".omg/evidence/gate.json"],
        "progress": {"total": 5, "completed": 3},
        "updated_at": "2026-03-01T12:00:00Z",
    }
    (state_dir / "background-verification.json").write_text(
        json.dumps(verification_state), encoding="utf-8"
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "verification blocked" in lowered
    assert "2 blockers" in lowered


def test_hud_renders_session_health_from_state_file(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    health_dir = project / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)
    (health_dir / "run-1.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "run-1",
            "contamination_risk": 0.15,
            "overthinking_score": 0.32,
            "context_health": 0.85,
            "verification_status": "ok",
            "recommended_action": "continue",
            "thresholds": {},
            "updated_at": "2026-03-08T12:00:00Z",
        }),
        encoding="utf-8",
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "contam:" in lowered
    assert "overthink:" in lowered
    assert "health:" in lowered


def test_hud_renders_session_health_block_badge(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    health_dir = project / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)
    (health_dir / "run-2.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "run-2",
            "contamination_risk": 0.8,
            "overthinking_score": 0.1,
            "context_health": 0.6,
            "verification_status": "ok",
            "recommended_action": "block",
            "thresholds": {},
            "updated_at": "2026-03-08T12:00:00Z",
        }),
        encoding="utf-8",
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "block" in lowered
    assert "contam:80%" in lowered


def test_hud_renders_session_health_from_stdin(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    project.mkdir(parents=True)

    payload = _stdin_payload(project)
    payload["session_health"] = {
        "schema": "SessionHealth",
        "schema_version": "1.0.0",
        "run_id": "stdin-1",
        "contamination_risk": 0.45,
        "overthinking_score": 0.55,
        "context_health": 0.7,
        "verification_status": "running",
        "recommended_action": "reflect",
        "thresholds": {},
        "updated_at": "2026-03-08T12:00:00Z",
    }

    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "contam:45%" in lowered
    assert "overthink:55%" in lowered
    assert "health:70%" in lowered
    assert "reflect" in lowered


def test_hud_omits_session_health_when_no_state(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    project.mkdir(parents=True)

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "contam:" not in lowered
    assert "overthink:" not in lowered


def test_hud_marks_stale_session_health(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    health_dir = project / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)

    stale_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    (health_dir / "stale-1.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "stale-1",
            "contamination_risk": 0.1,
            "overthinking_score": 0.1,
            "context_health": 0.9,
            "verification_status": "ok",
            "recommended_action": "continue",
            "thresholds": {},
            "updated_at": stale_time,
        }),
        encoding="utf-8",
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "[stale]" in lowered, f"Expected '[STALE]' marker in HUD output: {out.stdout}"


def test_hud_fresh_session_health_no_stale_marker(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    health_dir = project / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)

    fresh_time = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    (health_dir / "fresh-1.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "fresh-1",
            "contamination_risk": 0.1,
            "overthinking_score": 0.1,
            "context_health": 0.9,
            "verification_status": "ok",
            "recommended_action": "continue",
            "thresholds": {},
            "updated_at": fresh_time,
        }),
        encoding="utf-8",
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "contam:" in lowered
    assert "[stale]" not in lowered


def test_hud_displays_mode_from_mode_state_file(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    state_dir = project / ".omg" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "mode.json").write_text(json.dumps({"mode": "focused"}), encoding="utf-8")

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    assert "mode:focused" in out.stdout.lower()


# --- Task 10: HUD progress step/total rendering ---


def test_hud_renders_verification_progress_step_total(tmp_path: Path):
    """HUD renders step/total from verification progress state."""
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    state_dir = project / ".omg" / "state"
    state_dir.mkdir(parents=True)

    verification_state = {
        "schema": "BackgroundVerificationState",
        "schema_version": 2,
        "run_id": "test-progress-1",
        "status": "running",
        "blockers": [],
        "evidence_links": [],
        "progress": {"step": 3, "total": 7, "current_stage": "lsp_clean"},
        "updated_at": "2026-03-09T12:00:00Z",
    }
    (state_dir / "background-verification.json").write_text(
        json.dumps(verification_state), encoding="utf-8"
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "3/7" in lowered, f"Expected step/total '3/7' in HUD output: {out.stdout}"
    assert "verification running" in lowered


def test_hud_renders_verification_progress_with_current_stage(tmp_path: Path):
    """HUD renders current_stage name when available in progress."""
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    state_dir = project / ".omg" / "state"
    state_dir.mkdir(parents=True)

    verification_state = {
        "schema": "BackgroundVerificationState",
        "schema_version": 2,
        "run_id": "test-progress-2",
        "status": "running",
        "blockers": [],
        "evidence_links": [],
        "progress": {"step": 5, "total": 9, "current_stage": "security_scan"},
        "updated_at": "2026-03-09T12:00:00Z",
    }
    (state_dir / "background-verification.json").write_text(
        json.dumps(verification_state), encoding="utf-8"
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "5/9" in lowered
    assert "security_scan" in lowered


def test_hud_renders_completed_verification_without_progress(tmp_path: Path):
    """HUD renders ok status without step/total noise when complete."""
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    state_dir = project / ".omg" / "state"
    state_dir.mkdir(parents=True)

    verification_state = {
        "schema": "BackgroundVerificationState",
        "schema_version": 2,
        "run_id": "test-done",
        "status": "ok",
        "blockers": [],
        "evidence_links": [".omg/evidence/final.json"],
        "progress": {"step": 7, "total": 7},
        "updated_at": "2026-03-09T12:00:00Z",
    }
    (state_dir / "background-verification.json").write_text(
        json.dumps(verification_state), encoding="utf-8"
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    assert out.returncode == 0
    lowered = out.stdout.lower()
    assert "verification ok" in lowered


def test_hud_prefers_active_run_verification_state(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    state_dir = project / ".omg" / "state"
    verification_dir = state_dir / "verification_controller"
    verification_dir.mkdir(parents=True)
    shadow_dir = project / ".omg" / "shadow"
    shadow_dir.mkdir(parents=True)
    (shadow_dir / "active-run").write_text("run-active\n", encoding="utf-8")

    (verification_dir / "run-active.json").write_text(
        json.dumps({
            "schema": "VerificationControllerState",
            "schema_version": "1.0.0",
            "run_id": "run-active",
            "status": "running",
            "blockers": [],
            "evidence_links": [],
            "progress": {"step": 2, "total": 4, "current_stage": "tests"},
            "updated_at": "2026-03-10T12:00:00Z",
        }),
        encoding="utf-8",
    )
    (state_dir / "background-verification.json").write_text(
        json.dumps({
            "schema": "BackgroundVerificationState",
            "schema_version": 2,
            "run_id": "run-stale",
            "status": "blocked",
            "blockers": ["old blocker"],
            "evidence_links": [],
            "progress": {},
            "updated_at": "2026-03-01T12:00:00Z",
        }),
        encoding="utf-8",
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    lowered = out.stdout.lower()
    assert "verification running" in lowered
    assert "2/4" in lowered
    assert "verification blocked" not in lowered


def test_hud_prefers_session_health_latest_file(tmp_path: Path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    project = tmp_path / "project"
    health_dir = project / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)
    (health_dir / "zz-old.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "zz-old",
            "contamination_risk": 0.9,
            "overthinking_score": 0.9,
            "context_health": 0.1,
            "verification_status": "blocked",
            "recommended_action": "block",
            "thresholds": {},
            "updated_at": "2026-03-01T12:00:00Z",
        }),
        encoding="utf-8",
    )
    (health_dir / "latest.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "latest",
            "contamination_risk": 0.12,
            "overthinking_score": 0.18,
            "context_health": 0.88,
            "verification_status": "ok",
            "recommended_action": "continue",
            "thresholds": {},
            "updated_at": "2026-03-10T12:00:00Z",
        }),
        encoding="utf-8",
    )

    payload = _stdin_payload(project)
    out = _run_hud(payload, {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(claude)})
    lowered = out.stdout.lower()
    assert "contam:12%" in lowered
    assert "overthink:18%" in lowered
    assert "health:88%" in lowered
    assert "block" not in lowered
