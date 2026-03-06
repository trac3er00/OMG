"""Security assertions for project-level permission defaults."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_permissions() -> dict:
    settings = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
    return settings["permissions"]


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
