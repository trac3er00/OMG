"""Security assertions for project-level permission defaults."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_settings() -> dict:
    return json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))


def _load_permissions() -> dict:
    return _load_settings()["permissions"]


def test_network_and_remote_commands_require_ask():
    permissions = _load_permissions()
    allow = set(permissions["allow"])
    ask = set(permissions["ask"])

    for command in [
        "Bash(curl *)",
        "Bash(wget *)",
        "Bash(ssh *)",
        "Bash(scp *)",
        "Bash(rsync *)",
    ]:
        assert command in ask
        assert command not in allow


def test_container_and_cluster_commands_require_ask():
    permissions = _load_permissions()
    allow = set(permissions["allow"])
    ask = set(permissions["ask"])

    for command in [
        "Bash(docker *)",
        "Bash(docker-compose *)",
        "Bash(kubectl exec *)",
        "Bash(kubectl edit *)",
        "Bash(kubectl patch *)",
    ]:
        assert command in ask
        assert command not in allow


def test_sensitive_interpreters_and_env_require_ask():
    permissions = _load_permissions()
    allow = set(permissions["allow"])
    ask = set(permissions["ask"])

    for command in [
        "Bash(env *)",
        "Bash(node *)",
        "Bash(python *)",
        "Bash(python3 *)",
        "Bash(chmod *)",
        "Bash(chown *)",
    ]:
        assert command in ask
        assert command not in allow


def test_pretool_use_registers_security_guards_before_injection():
    settings = _load_settings()
    entries = settings["hooks"]["PreToolUse"]

    commands_by_matcher = {
        entry.get("matcher", ""): [hook["command"] for hook in entry["hooks"]]
        for entry in entries
    }

    assert commands_by_matcher["Bash"] == ['python3 "$HOME/.claude/hooks/firewall.py"']
    assert commands_by_matcher["Read|Write|Edit|MultiEdit"] == [
        'python3 "$HOME/.claude/hooks/secret-guard.py"'
    ]
    assert commands_by_matcher[""] == ['python3 "$HOME/.claude/hooks/pre-tool-inject.py"']
