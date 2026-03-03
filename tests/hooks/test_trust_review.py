"""Tests for trust review scoring and manifest output."""

import json
from pathlib import Path

from hooks.trust_review import review_config_change, write_trust_manifest


def test_trust_review_detects_dangerous_permission_change():
    old = {"permissions": {"allow": ["Read"]}, "hooks": {"PreToolUse": [{}]}}
    new = {
        "permissions": {"allow": ["Read", "Bash(sudo:*)"]},
        "hooks": {"PreToolUse": []},
    }
    review = review_config_change("settings.json", old, new)
    assert review["verdict"] == "deny"
    assert review["risk_level"] == "critical"
    assert review["risk_score"] >= 80


def test_trust_review_manifest_written(tmp_path: Path):
    review = review_config_change("settings.json", {}, {"hooks": {"PreToolUse": []}})
    path = write_trust_manifest(str(tmp_path), review)
    assert Path(path).exists()
    data = json.loads(Path(path).read_text())
    assert data["version"] == "omg-v1"
    assert "signature" in data
    assert "last_review" in data


def test_trust_review_counts_nested_hook_commands():
    old = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": "python3 hook-a.py"},
                        {"type": "command", "command": "python3 hook-b.py"},
                    ]
                }
            ]
        }
    }
    new = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": "python3 hook-a.py"},
                    ]
                }
            ]
        }
    }
    review = review_config_change("settings.json", old, new)
    assert review["hook_changes"]["old_hook_count"] == 2
    assert review["hook_changes"]["new_hook_count"] == 1
    assert "Stop" in review["hook_changes"]["modified_events"]


def test_trust_review_marks_modified_hooks_for_manual_review():
    old = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 old.py"}]}
            ]
        }
    }
    new = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 new.py"}]}
            ]
        }
    }
    review = review_config_change("settings.json", old, new)
    assert "hook-diff-review" in review["controls"]
    assert any("Hook definitions modified" in reason for reason in review["reasons"])
