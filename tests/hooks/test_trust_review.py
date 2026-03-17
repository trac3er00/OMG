"""Tests for trust review scoring and manifest output."""

import json
from pathlib import Path

from hooks.trust_review import regenerate_trust_manifest, review_config_change, write_trust_manifest


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


def test_trust_review_detects_space_syntax_dangerous_permission_change():
    old = {"permissions": {"allow": ["Read"]}}
    new = {"permissions": {"allow": ["Read", "Bash(curl *)", "Bash(ssh *)"]}}

    review = review_config_change("settings.json", old, new)

    assert review["verdict"] == "deny"
    assert review["risk_level"] == "critical"
    assert review["risk_score"] >= 80


def test_trust_review_blocks_high_risk_mcp_config_change():
    old = {"mcpServers": {}}
    new = {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/example"],
            },
            "chrome-devtools": {
                "command": "npx",
                "args": ["-y", "chrome-devtools-mcp@latest"],
            },
        }
    }

    review = review_config_change(".mcp.json", old, new)

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


def test_regenerate_trust_manifest_uses_snapshot_and_live_settings(tmp_path: Path):
    trust_dir = tmp_path / ".omg" / "trust"
    trust_dir.mkdir(parents=True)
    (trust_dir / "last-settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read"]}}),
        encoding="utf-8",
    )
    (tmp_path / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read", "Bash(sudo:*)"]}}),
        encoding="utf-8",
    )

    out = regenerate_trust_manifest(str(tmp_path), "settings.json")

    assert Path(out["manifest_path"]).exists()
    assert out["review"]["verdict"] == "deny"
    assert out["review"]["risk_level"] == "critical"
    saved_snapshot = json.loads((trust_dir / "last-settings.json").read_text(encoding="utf-8"))
    assert saved_snapshot["permissions"]["allow"][-1] == "Bash(sudo:*)"


def test_regenerate_trust_manifest_preserves_space_syntax_deny(tmp_path: Path):
    trust_dir = tmp_path / ".omg" / "trust"
    trust_dir.mkdir(parents=True)
    (trust_dir / "last-settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read"]}}),
        encoding="utf-8",
    )
    (tmp_path / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read", "Bash(sudo *)"]}}),
        encoding="utf-8",
    )

    out = regenerate_trust_manifest(str(tmp_path), "settings.json")
    assert out["review"]["verdict"] == "deny"
