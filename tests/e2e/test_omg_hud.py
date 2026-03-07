"""Tests for OMG HUD compatibility behavior."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from datetime import UTC, datetime, timedelta
from typing import cast


ROOT = Path(__file__).resolve().parents[2]
HUD = ROOT / "hud" / "omg-hud.mjs"


def _run_hud(payload: dict[str, object], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    merged_env.update(env)
    return subprocess.run(
        ["node", str(HUD)],
        input=json.dumps(payload),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


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
