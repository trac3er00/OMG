"""Regression tests for scripts/settings-merge.py."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settings-merge.py"


def _run(existing_path: Path, new_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(existing_path), str(new_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_merge_deduplicates_configchange_direct_command_entries(tmp_path: Path):
    entry = {"type": "command", "command": "python3 \"$HOME/.claude/hooks/config-guard.py\""}
    existing = {"hooks": {"ConfigChange": [entry]}}
    new = {"hooks": {"ConfigChange": [entry]}}
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    config_change = merged["hooks"]["ConfigChange"]
    assert len(config_change) == 1
    assert config_change[0]["command"] == entry["command"]


def test_merge_adds_missing_mcp_servers(tmp_path: Path):
    existing = {"mcpServers": {"filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}}}
    new = {
        "mcpServers": {
            "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
            "websearch": {"command": "npx", "args": ["-y", "exa-mcp-server"]},
            "chrome-devtools": {"command": "npx", "args": ["-y", "chrome-devtools-mcp@latest"]},
        }
    }
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    assert set(merged["mcpServers"].keys()) == {"filesystem", "context7", "websearch", "chrome-devtools"}


def test_merge_mcp_server_keeps_existing_and_unions_args_and_env(tmp_path: Path):
    existing = {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                "env": {"ROOT": "."},
            }
        }
    }
    new = {
        "mcpServers": {
            "filesystem": {
                "command": "node",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", ".", "src"],
                "env": {"ROOT": "overridden", "MODE": "readonly"},
                "extra": "value",
            }
        }
    }
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    filesystem = merged["mcpServers"]["filesystem"]
    assert filesystem["command"] == "npx"
    assert filesystem["args"] == ["-y", "@modelcontextprotocol/server-filesystem", ".", "src"]
    assert filesystem["env"] == {"ROOT": ".", "MODE": "readonly"}
    assert filesystem["extra"] == "value"


def test_merge_replaces_stale_hook_command_variants(tmp_path: Path):
    existing = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'bun "$HOME/.claude/hooks/firewall.ts"',
                        }
                    ],
                }
            ]
        }
    }
    new = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$HOME/.claude/hooks/firewall.py"',
                        }
                    ],
                }
            ]
        }
    }
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    hooks = merged["hooks"]["PreToolUse"]
    assert len(hooks) == 1
    command = hooks[0]["hooks"][0]["command"]
    assert command == 'python3 "$HOME/.claude/hooks/firewall.py"'


def test_merge_replaces_duplicate_stale_hook_entries(tmp_path: Path):
    existing = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$HOME/.claude/hooks/session-start.py"',
                        }
                    ],
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": '"$HOME/.claude/hooks/session-start.ts"',
                        }
                    ],
                },
            ]
        }
    }
    new = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$HOME/.claude/hooks/session-start.py"',
                        }
                    ],
                }
            ]
        }
    }
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    hooks = merged["hooks"]["SessionStart"]
    assert len(hooks) == 1
    command = hooks[0]["hooks"][0]["command"]
    assert command == 'python3 "$HOME/.claude/hooks/session-start.py"'


def test_merge_normalizes_hook_identity_aliases(tmp_path: Path):
    existing = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": '"$HOME/.claude/hooks/stop-dispatcher.ts"',
                        }
                    ],
                }
            ]
        }
    }
    new = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$HOME/.claude/hooks/stop_dispatcher.py"',
                        }
                    ],
                }
            ]
        }
    }
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    hooks = merged["hooks"]["Stop"]
    assert len(hooks) == 1
    command = hooks[0]["hooks"][0]["command"]
    assert command == 'python3 "$HOME/.claude/hooks/stop_dispatcher.py"'


def test_merge_treats_blank_and_missing_matchers_as_same_group(tmp_path: Path):
    existing = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": '"$HOME/.claude/hooks/stop-dispatcher.ts"',
                        }
                    ],
                }
            ]
        }
    }
    new = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$HOME/.claude/hooks/stop_dispatcher.py"',
                        }
                    ],
                }
            ]
        }
    }
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    hooks = merged["hooks"]["Stop"]
    assert len(hooks) == 1
    assert hooks[0]["matcher"] == ""
    command = hooks[0]["hooks"][0]["command"]
    assert command == 'python3 "$HOME/.claude/hooks/stop_dispatcher.py"'


def test_merge_moves_managed_permission_to_new_category(tmp_path: Path):
    existing = {"permissions": {"allow": ["Bash(curl *)"], "ask": [], "deny": []}}
    new = {"permissions": {"allow": [], "ask": ["Bash(curl *)"], "deny": []}}
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    assert "Bash(curl *)" not in merged["permissions"]["allow"]
    assert "Bash(curl *)" in merged["permissions"]["ask"]


def test_merge_updates_omg_version_and_preset_while_preserving_feature_overrides(tmp_path: Path):
    existing = {
        "_omg": {
            "_version": "2.0.0",
            "features": {
                "MEMORY_AUTOSTART": False,
                "SETUP_WIZARD": True,
            },
        }
    }
    new = {
        "_omg": {
            "_version": "2.0.1",
            "preset": "safe",
            "features": {
                "MEMORY_AUTOSTART": True,
                "SETUP": True,
                "SETUP_WIZARD": True,
            },
        }
    }
    existing_path = tmp_path / "existing.json"
    new_path = tmp_path / "new.json"
    existing_path.write_text(json.dumps(existing), encoding="utf-8")
    new_path.write_text(json.dumps(new), encoding="utf-8")

    proc = _run(existing_path, new_path)
    assert proc.returncode == 0, proc.stderr

    merged = json.loads(existing_path.read_text(encoding="utf-8"))
    omg = merged["_omg"]
    assert omg["_version"] == "2.0.1"
    assert omg["preset"] == "safe"
    assert omg["features"]["MEMORY_AUTOSTART"] is False
    assert omg["features"]["SETUP"] is True
    assert omg["features"]["SETUP_WIZARD"] is True
