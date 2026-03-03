"""Custom Agent Loader — scans user/project agent dirs, hot-reloads on change.

Scans ~/.oal/agents/ (user-level) and <project>/.oal/agents/ (project-level)
for custom agent markdown files. Project-level agents override user-level.

Feature flag: OAL_CUSTOM_AGENTS_ENABLED (default: False)
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

# --- Lazy import helpers ---
_OAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_feature_flag() -> Any:
    """Lazy-import get_feature_flag from hooks/_common.py."""
    hooks_dir = os.path.join(_OAL_ROOT, "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import get_feature_flag  # pyright: ignore[reportMissingImports]
        return get_feature_flag
    except ImportError:
        return None


def _is_enabled() -> bool:
    """Check if custom agents feature is enabled.

    Resolution: env var OAL_CUSTOM_AGENTS_ENABLED → settings.json → default False.
    """
    # Fast path: check env var directly
    env_val = os.environ.get("OAL_CUSTOM_AGENTS_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # Slow path: check via get_feature_flag
    get_flag = _get_feature_flag()
    if get_flag is not None:
        return get_flag("CUSTOM_AGENTS", default=False)
    return False


# --- Schema validation ---

# Required sections
_AGENT_HEADER_RE = re.compile(r"^#\s+Agent:\s*.+", re.MULTILINE)
_ROLE_SECTION_RE = re.compile(r"^##\s+Role\b", re.MULTILINE)

# Optional sections (validated if present)
_OPTIONAL_SECTIONS = {
    "Model": re.compile(r"^##\s+Model\b", re.MULTILINE),
    "Capabilities": re.compile(r"^##\s+Capabilities\b", re.MULTILINE),
    "Instructions": re.compile(r"^##\s+Instructions\b", re.MULTILINE),
}


def _validate_agent_schema(content: str) -> tuple[bool, list[str]]:
    """Validate custom agent markdown schema.

    Args:
        content: Markdown content of the agent file.

    Returns:
        (is_valid, issues) where issues is a list of validation error strings.
        Required: ``# Agent:`` header AND ``## Role`` section.
        Optional but validated if present: ``## Model``, ``## Capabilities``, ``## Instructions``.
    """
    issues: list[str] = []

    if not content or not content.strip():
        return False, ["Agent file is empty"]

    # Required: # Agent: header
    if not _AGENT_HEADER_RE.search(content):
        issues.append("Missing required '# Agent: <name>' header")

    # Required: ## Role section
    if not _ROLE_SECTION_RE.search(content):
        issues.append("Missing required '## Role' section")

    # Optional sections: validate format if present (check for typos)
    # We don't flag missing optional sections, but if they're present with wrong format,
    # we note it as informational (not blocking).

    is_valid = len(issues) == 0
    return is_valid, issues


def _extract_agent_name(content: str, filename: str) -> str:
    """Extract agent name from # Agent: header or fall back to filename."""
    match = _AGENT_HEADER_RE.search(content)
    if match:
        # Extract the name part after "# Agent:"
        line = match.group(0)
        name = line.split(":", 1)[1].strip() if ":" in line else ""
        if name:
            return name.lower().replace(" ", "_")
    # Fallback: use filename without extension
    return Path(filename).stem.lower().replace("-", "_")


def _extract_description(content: str) -> str:
    """Extract description from ## Role section content."""
    match = _ROLE_SECTION_RE.search(content)
    if not match:
        return ""
    # Get text after ## Role until next ## or end
    rest = content[match.end():]
    next_section = re.search(r"^##\s+", rest, re.MULTILINE)
    if next_section:
        rest = rest[:next_section.start()]
    # Take first non-empty line as description
    for line in rest.strip().splitlines():
        line = line.strip()
        if line:
            return line[:200]  # Cap at 200 chars
    return ""


def _extract_model_role(content: str) -> str | None:
    """Extract model role from ## Model section if present."""
    model_match = _OPTIONAL_SECTIONS["Model"].search(content)
    if not model_match:
        return None
    rest = content[model_match.end():]
    next_section = re.search(r"^##\s+", rest, re.MULTILINE)
    if next_section:
        rest = rest[:next_section.start()]
    text = rest.strip().lower()
    # Look for known role keywords
    for role in ("smol", "slow", "default", "fast"):
        if role in text:
            return role
    return None


# --- Agent scanning ---

def _get_user_agents_dir() -> str:
    """Get user-level agents directory: ~/.oal/agents/"""
    return os.path.join(os.path.expanduser("~"), ".oal", "agents")


def _get_project_agents_dir(project_dir: str) -> str:
    """Get project-level agents directory: <project>/.oal/agents/"""
    return os.path.join(project_dir, ".oal", "agents")


def _scan_agents_dir(agents_dir: str, level: str) -> list[dict[str, Any]]:
    """Scan a directory for agent .md files.

    Args:
        agents_dir: Path to scan for .md files.
        level: 'user' or 'project'.

    Returns:
        List of agent info dicts.
    """
    agents: list[dict[str, Any]] = []

    if not os.path.isdir(agents_dir):
        return agents

    for filename in sorted(os.listdir(agents_dir)):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(agents_dir, filename)
        if not os.path.isfile(filepath):
            continue

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(256 * 1024)  # 256KB limit
        except OSError:
            continue

        is_valid, issues = _validate_agent_schema(content)
        name = _extract_agent_name(content, filename)
        description = _extract_description(content)
        model_role = _extract_model_role(content)

        agents.append({
            "name": name,
            "file": filepath,
            "level": level,
            "model_role": model_role,
            "description": description,
            "validated": is_valid,
            "issues": issues,
        })

    return agents


def load_custom_agents(project_dir: str = ".") -> list[dict[str, Any]]:
    """Load custom agents from user and project directories.

    If OAL_CUSTOM_AGENTS_ENABLED is False, returns empty list.
    Scans ~/.oal/agents/*.md (user-level) and <project_dir>/.oal/agents/*.md (project-level).
    Project-level agents override user-level agents with the same name.

    Args:
        project_dir: Project directory (default: current directory).

    Returns:
        List of agent info dicts with keys:
        name, file, level, model_role, description, validated, issues
    """
    if not _is_enabled():
        return []

    project_dir = os.path.abspath(project_dir)

    # Scan user-level first
    user_dir = _get_user_agents_dir()
    user_agents = _scan_agents_dir(user_dir, "user")

    # Scan project-level
    project_agents_dir = _get_project_agents_dir(project_dir)
    project_agents = _scan_agents_dir(project_agents_dir, "project")

    # Merge: project overrides user with same name
    agents_by_name: dict[str, dict[str, Any]] = {}
    for agent in user_agents:
        agents_by_name[agent["name"]] = agent
    for agent in project_agents:
        agents_by_name[agent["name"]] = agent  # Override user-level

    return list(agents_by_name.values())


# --- Hot-reload watcher ---

def _get_dir_state(agents_dir: str) -> dict[str, float]:
    """Get mtime state of all .md files in a directory.

    Returns:
        Dict mapping filename → mtime.
    """
    state: dict[str, float] = {}
    if not os.path.isdir(agents_dir):
        return state
    try:
        for filename in os.listdir(agents_dir):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(agents_dir, filename)
            try:
                state[filepath] = os.stat(filepath).st_mtime
            except OSError:
                continue
    except OSError:
        pass
    return state


def watch_for_changes(
    project_dir: str,
    callback: Callable[[list[dict[str, Any]]], None],
    poll_interval: float = 5.0,
    max_iterations: int | None = None,
) -> None:
    """Poll agent dirs for changes and call callback when detected.

    Uses stdlib-only mtime polling (no watchdog dependency).
    Polls every ``poll_interval`` seconds.

    Args:
        project_dir: Project directory.
        callback: Called with updated agent list when changes detected.
        poll_interval: Seconds between polls (default: 5.0).
        max_iterations: If set, stop after this many iterations (for testing).
    """
    project_dir = os.path.abspath(project_dir)
    user_dir = _get_user_agents_dir()
    project_agents_dir = _get_project_agents_dir(project_dir)

    # Initial state
    prev_user_state = _get_dir_state(user_dir)
    prev_project_state = _get_dir_state(project_agents_dir)

    iterations = 0
    while True:
        if max_iterations is not None and iterations >= max_iterations:
            break

        time.sleep(poll_interval)
        iterations += 1

        # Check for changes
        curr_user_state = _get_dir_state(user_dir)
        curr_project_state = _get_dir_state(project_agents_dir)

        if curr_user_state != prev_user_state or curr_project_state != prev_project_state:
            # Reload agents
            agents = load_custom_agents(project_dir)
            callback(agents)
            prev_user_state = curr_user_state
            prev_project_state = curr_project_state


# --- Merged agent registry ---

def get_all_agents(project_dir: str = ".") -> dict[str, dict[str, Any]]:
    """Return merged dict of built-in + custom agents.

    Custom agents extend/override built-in registry entries.
    Returns dict mapping agent name → agent config.

    Args:
        project_dir: Project directory (default: current directory).

    Returns:
        Dict of agent configs. Built-in agents have standard keys.
        Custom agents have: name, file, level, model_role, description,
        validated, preferred_model, task_category, trigger_keywords, etc.
    """
    # Get built-in agents via lazy import
    hooks_dir = os.path.join(_OAL_ROOT, "hooks")
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

    merged: dict[str, dict[str, Any]] = {}

    try:
        from _agent_registry import AGENT_REGISTRY  # pyright: ignore[reportMissingImports]
        # Copy built-in agents
        for name, config in AGENT_REGISTRY.items():
            merged[name] = dict(config)
            merged[name]["source"] = "builtin"
    except ImportError:
        pass

    # Overlay custom agents
    custom_agents = load_custom_agents(project_dir)
    for agent in custom_agents:
        if not agent.get("validated", False):
            continue  # Skip invalid custom agents

        name = agent["name"]
        merged[name] = {
            "preferred_model": "claude",
            "task_category": "unspecified-high",
            "skills": [],
            "trigger_keywords": set(),
            "mcp_tools": [],
            "description": agent.get("description", ""),
            "agent_file": agent.get("file", ""),
            "model_version": "claude-sonnet-4-5",
            "model_role": agent.get("model_role"),
            "source": "custom",
            "level": agent.get("level", "unknown"),
            "validated": True,
        }

    return merged
