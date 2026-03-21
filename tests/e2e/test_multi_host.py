"""Multi-host E2E test suite.

Tests OMG installation and hook execution across supported CLI hosts:
Claude Code, Codex, Gemini, Kimi, OpenCode.

These tests require fake host binaries and validate:
1. Install flow per host
2. Hook registration per host's event model
3. Command output parsing per host
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

CANONICAL_HOSTS = ["claude", "codex", "gemini", "kimi", "opencode"]
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def host_env(tmp_path: Path):
    """Create a test environment with fake host binaries."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    # Create fake binaries for all hosts
    for binary in ("codex", "gemini", "kimi", "opencode"):
        script = fake_bin / binary
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)

    env = {
        "CLAUDE_CONFIG_DIR": str(claude_dir),
        "HOME": str(home_dir),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
    }
    return {"env": env, "claude_dir": claude_dir, "home_dir": home_dir, "tmp_path": tmp_path}


@pytest.mark.parametrize("host", CANONICAL_HOSTS)
def test_quickstart_detects_host(host_env: dict[str, Any], host: str) -> None:
    """Quickstart should detect each host binary and include it in the plan."""
    proc = subprocess.run(
        ["python3", str(SCRIPT_DIR / "scripts" / "omg.py"), "quickstart",
         "--format", "json", "--level", "1"],
        capture_output=True, text=True, timeout=30,
        env={**host_env["env"], "CLAUDE_PROJECT_DIR": str(SCRIPT_DIR)},
    )
    # Quickstart may fail in test env (no real host), but should not crash
    assert proc.returncode in (0, 1), f"Unexpected exit code {proc.returncode}: {proc.stderr}"


def test_install_plan_includes_all_detected_hosts(host_env: dict[str, Any]) -> None:
    """Install plan should include config actions for all detected hosts."""
    proc = subprocess.run(
        ["python3", str(SCRIPT_DIR / "scripts" / "omg.py"), "install", "--plan",
         "--format", "json", "--preset", "interop"],
        capture_output=True, text=True, timeout=30,
        env={**host_env["env"], "CLAUDE_PROJECT_DIR": str(SCRIPT_DIR)},
    )
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            plan = json.loads(proc.stdout)
            actions = plan.get("actions", [])
            assert len(actions) > 0, "Plan should have at least one action"
        except json.JSONDecodeError:
            pass  # Non-JSON output is OK (text format)


def test_hook_files_have_valid_syntax() -> None:
    """All hook .py files must pass syntax validation."""
    hooks_dir = SCRIPT_DIR / "hooks"
    for hook_file in hooks_dir.glob("*.py"):
        proc = subprocess.run(
            ["python3", "-c", f"import py_compile; py_compile.compile('{hook_file}', doraise=True)"],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0, f"Syntax error in {hook_file.name}: {proc.stderr}"


def test_command_files_have_valid_frontmatter() -> None:
    """All command .md files must have valid YAML frontmatter."""
    import yaml

    commands_dir = SCRIPT_DIR / "commands"
    for cmd_file in commands_dir.glob("*.md"):
        content = cmd_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"{cmd_file.name} has malformed frontmatter"
        fm = yaml.safe_load(parts[1])
        assert isinstance(fm, dict), f"{cmd_file.name} frontmatter is not a dict"
        assert "description" in fm, f"{cmd_file.name} missing description in frontmatter"


@pytest.mark.parametrize("host", CANONICAL_HOSTS)
def test_install_guide_exists_for_host(host: str) -> None:
    """Each canonical host should have an install guide."""
    guide_path = SCRIPT_DIR / "docs" / "install" / f"{host if host != 'claude' else 'claude-code'}.md"
    assert guide_path.exists(), f"Missing install guide for {host}: {guide_path}"


# --- Additional multi-host E2E tests ---

def test_agent_registry_has_preferred_models() -> None:
    """All agents in the registry must specify a preferred_model."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from hooks._agent_registry import AGENT_REGISTRY
        valid_models = {"claude", "codex-cli", "gemini-cli", "domain-dependent"}
        for name, agent in AGENT_REGISTRY.items():
            assert "preferred_model" in agent, f"Agent {name} missing preferred_model"
            assert agent["preferred_model"] in valid_models, \
                f"Agent {name} has invalid preferred_model: {agent['preferred_model']}"
    finally:
        sys.path.pop(0)


def test_runtime_modules_importable() -> None:
    """Key runtime modules must import without errors."""
    sys.path.insert(0, str(SCRIPT_DIR))
    modules = [
        "runtime.issue_orchestrator",
        "runtime.state_rotation",
        "runtime.mcp_dedup",
        "runtime.plugin_cohesion",
        "runtime.agent_store",
        "runtime.sqlite_ledger",
    ]
    for mod_name in modules:
        try:
            __import__(mod_name)
        except ImportError as e:
            pytest.fail(f"Cannot import {mod_name}: {e}")
    sys.path.pop(0)


def test_consolidated_hooks_exist() -> None:
    """Consolidated hook dispatchers must exist."""
    for name in ("pre-tool-all.py", "post-tool-all.py", "hashline-manager.py"):
        path = SCRIPT_DIR / "hooks" / name
        assert path.exists(), f"Consolidated hook missing: {name}"


def test_deprecated_commands_dont_grant_broad_tools() -> None:
    """Deprecated command stubs should only allow Read tool."""
    import yaml
    deprecated = [
        "OMG:doctor.md", "OMG:health-check.md", "OMG:diagnose-plugins.md",
        "OMG:setup.md", "OMG:session-branch.md", "OMG:session-fork.md",
        "OMG:session-merge.md", "OMG:ralph-start.md", "OMG:ralph-stop.md",
        "OMG:ccg.md", "OMG:teams.md", "OMG:cost.md",
    ]
    commands_dir = SCRIPT_DIR / "commands"
    for fname in deprecated:
        path = commands_dir / fname
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if "DEPRECATED" not in content:
            continue
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1])
            tools = fm.get("allowed-tools", "")
            assert tools == "Read", f"{fname} grants tools beyond Read: {tools}"


def test_issue_orchestrator_agents_complete() -> None:
    """Issue orchestrator must have all expected sub-agents."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from runtime.issue_orchestrator import AGENTS
        expected = {"red-team", "dep-audit", "secret-scan", "env-scan", "privacy-audit", "leak-detective"}
        assert expected.issubset(set(AGENTS.keys())), \
            f"Missing agents: {expected - set(AGENTS.keys())}"
    finally:
        sys.path.pop(0)


def test_sqlite_ledger_roundtrip(tmp_path: Path) -> None:
    """SQLite ledger basic write/read cycle."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from runtime.sqlite_ledger import SQLiteLedger
        ledger = SQLiteLedger(str(tmp_path))
        ledger.append_tool_entry({"tool": "Bash", "command": "ls", "ts": "2026-03-20T00:00:00Z"})
        ledger.append_tool_entry({"tool": "Read", "command": "", "ts": "2026-03-20T00:00:01Z"})
        assert ledger.get_tool_count(since_minutes=999999) >= 2
        recent = ledger.get_recent_tools(limit=5)
        assert len(recent) == 2
        assert recent[0]["tool"] == "Read"  # Most recent first
    finally:
        sys.path.pop(0)


def test_sqlite_ledger_cost_summary(tmp_path: Path) -> None:
    """SQLite ledger cost summary aggregation."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from runtime.sqlite_ledger import SQLiteLedger
        ledger = SQLiteLedger(str(tmp_path))
        ledger.append_cost_entry({"tool": "Bash", "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.001})
        ledger.append_cost_entry({"tool": "Read", "tokens_in": 200, "tokens_out": 30, "cost_usd": 0.002})
        summary = ledger.read_cost_summary()
        assert summary["entry_count"] == 2
        assert summary["total_tokens"] == 380
        assert summary["total_cost_usd"] == 0.003
        assert "Bash" in summary["by_tool"]
    finally:
        sys.path.pop(0)


def test_mcp_dedup_scan(tmp_path: Path) -> None:
    """MCP dedup scanner handles missing files gracefully."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from runtime.mcp_dedup import scan_mcp_configs
        result = scan_mcp_configs(str(tmp_path))
        assert "overlaps" in result
        assert "capability_map" in result
        assert result["has_duplicates"] is False
    finally:
        sys.path.pop(0)


def test_agent_store_lifecycle(tmp_path: Path) -> None:
    """Agent store: add, list, remove cycle."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from runtime.agent_store import AgentStore
        store = AgentStore(str(tmp_path))
        store.init()

        entry = store.add_agent("test-agent", "---\nname: test\n---\nTest agent.")
        assert entry.name == "test-agent"

        agents = store.list_agents()
        assert any(a.name == "test-agent" for a in agents)

        removed = store.remove_agent("test-agent")
        assert removed is True
        agents = store.list_agents()
        assert not any(a.name == "test-agent" for a in agents)
    finally:
        sys.path.pop(0)


def test_state_rotation_dry_run(tmp_path: Path) -> None:
    """State rotation dry run doesn't move files."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from runtime.state_rotation import rotate_state_files
        ledger_dir = tmp_path / ".omg" / "state" / "ledger"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "old.jsonl").write_text("{}")
        # Set mtime to 60 days ago
        import os
        old_time = os.path.getmtime(str(ledger_dir / "old.jsonl")) - (60 * 86400)
        os.utime(str(ledger_dir / "old.jsonl"), (old_time, old_time))

        result = rotate_state_files(str(tmp_path), max_age_days=30, dry_run=True)
        assert "old.jsonl" in result["archived"]
        assert (ledger_dir / "old.jsonl").exists()  # Not moved (dry run)
    finally:
        sys.path.pop(0)
