"""Tests for ConfigChange hook (§6.1)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def run_config_guard(payload: dict, project_dir: str):
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
        assert (Path(tmpdir) / ".oal" / "trust" / "manifest.lock.json").exists()


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
