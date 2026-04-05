"""Tests for ConfigChange hook (§6.1)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def run_config_guard(payload: dict[str, object], project_dir: str):
    proc = subprocess.run(
        ["python3", "hooks/config-guard.py"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": project_dir},
        check=False,
    )
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else None


def test_config_guard_monitors_settings():
    """§6.1: Should monitor settings.json changes."""
    with open("hooks/config-guard.py") as f:
        content = f.read()
    assert "settings.json" in content
    assert "DANGEROUS_IN_ALLOW" in content


def test_config_guard_checks_hook_count():
    """§6.1: Should warn if hooks are removed."""
    with open("hooks/config-guard.py") as f:
        content = f.read()
    assert "hook_count" in content


def test_config_guard_accepts_configchange_payload_shape():
    old = {"permissions": {"allow": ["Read"]}}
    new = {"permissions": {"allow": ["Read", "Bash(sudo:*)"]}}
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Path(tmpdir) / "settings.json"
        settings.write_text(json.dumps(new), encoding="utf-8")

        out = run_config_guard(
            {
                "source": "user",
                "file_path": str(settings),
                "old_config": old,
                "new_config": new,
            },
            tmpdir,
        )
        assert out is not None
        assert out["decision"] == "block"
        assert "Trust Review" in out["reason"]
        assert (Path(tmpdir) / ".omg" / "trust" / "manifest.lock.json").exists()


def test_config_guard_supports_legacy_tool_input_payload():
    old = {"permissions": {"allow": ["Read"]}}
    new = {"permissions": {"allow": ["Read", "Bash(sudo:*)"]}}
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Path(tmpdir) / "settings.json"
        settings.write_text(json.dumps(new), encoding="utf-8")

        out = run_config_guard(
            {
                "tool_input": {
                    "file_path": str(settings),
                    "old_config": old,
                }
            },
            tmpdir,
        )
        assert out is not None
        assert out["decision"] == "block"
        assert "Trust Review" in out["reason"]


def test_config_guard_reviews_high_risk_mcp_config_changes():
    old = {"mcpServers": {}}
    new = {
        "mcpServers": {
            "chrome-devtools": {
                "command": "npx",
                "args": ["-y", "chrome-devtools-mcp@latest"],
            }
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_config = Path(tmpdir) / ".mcp.json"
        mcp_config.write_text(json.dumps(new), encoding="utf-8")

        out = run_config_guard(
            {
                "source": "user",
                "file_path": str(mcp_config),
                "old_config": old,
                "new_config": new,
            },
            tmpdir,
        )
        assert out is not None
        assert out["decision"] == "block"
        assert "Trust Review" in out["reason"]
        assert (Path(tmpdir) / ".omg" / "trust" / "manifest.lock.json").exists()


def test_config_guard_ask_med_returns_explicit_pass_payload():
    old = {
        "hooks": {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "python3 old.py"}]}
            ]
        }
    }
    new = {
        "hooks": {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "python3 new.py"}]}
            ]
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Path(tmpdir) / "settings.json"
        settings.write_text(json.dumps(new), encoding="utf-8")
        (Path(tmpdir) / ".omg" / "trust").mkdir(parents=True, exist_ok=True)
        (Path(tmpdir) / ".omg" / "trust" / "last-settings.json").write_text(
            json.dumps(old),
            encoding="utf-8",
        )

        out = run_config_guard(
            {
                "source": "user",
                "file_path": str(settings),
                "old_config": old,
            },
            tmpdir,
        )

        assert out is not None
        assert out["decision"] == "pass"
        assert "Trust Review" in out["reason"]


def test_config_guard_scores_live_config_not_payload_override():
    live = {"permissions": {"allow": ["Read", "Bash(sudo:*)"]}}
    payload_new = {"permissions": {"allow": ["Read"]}}
    old = {"permissions": {"allow": ["Read"]}}
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Path(tmpdir) / "settings.json"
        settings.write_text(json.dumps(live), encoding="utf-8")
        (Path(tmpdir) / ".omg" / "trust").mkdir(parents=True, exist_ok=True)
        (Path(tmpdir) / ".omg" / "trust" / "last-settings.json").write_text(
            json.dumps(old),
            encoding="utf-8",
        )

        out = run_config_guard(
            {
                "source": "user",
                "file_path": str(settings),
                "old_config": old,
                "new_config": payload_new,
            },
            tmpdir,
        )

        assert out is not None
        assert out["decision"] == "block"
        assert "Bash(sudo:*)" in out["reason"]


def test_config_guard_bypassall_still_reviews_sensitive_permissions_change():
    old = {"permissions": {"allow": ["Read"]}}
    new = {"permissions": {"allow": ["Read", "Bash(curl:*)"]}}
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Path(tmpdir) / "settings.json"
        settings.write_text(json.dumps(new), encoding="utf-8")

        out = run_config_guard(
            {
                "source": "user",
                "file_path": str(settings),
                "old_config": old,
                "permission_mode": "bypassall",
            },
            tmpdir,
        )

        assert out is not None
        assert out["decision"] == "block"
        assert "Trust Review" in out["reason"]


def test_config_guard_blocks_when_settings_parse_fails_fail_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Path(tmpdir) / "settings.json"
        settings.write_text("{not-json", encoding="utf-8")

        out = run_config_guard(
            {
                "source": "user",
                "file_path": str(settings),
                "old_config": {},
            },
            tmpdir,
        )

        assert out is not None
        assert out["decision"] == "block"
        assert "parse failed" in out["reason"].lower()
