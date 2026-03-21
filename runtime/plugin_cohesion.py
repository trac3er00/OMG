"""Plugin Overlap & Cohesion Check.

Maps OMG commands → hooks → agents → MCPs dependency graph.
Detects external plugin conflicts and verifies internal cohesion.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def check_cohesion(project_dir: str) -> dict[str, Any]:
    """Run full cohesion analysis.

    Returns:
        {
            "status": "complete" | "gaps",
            "dependency_graph": {...},
            "external_conflicts": [...],
            "duplicate_hooks": [...],
            "orphaned_hooks": [...],
            "missing_hooks": [...],
            "gaps": [...],
        }
    """
    claude_dir = os.path.expanduser("~/.claude")

    # Build dependency graph
    commands = _scan_dir(os.path.join(project_dir, "commands"), "*.md")
    hooks = _scan_dir(os.path.join(project_dir, "hooks"), "*.py")
    agents = _scan_dir(os.path.join(project_dir, "agents"), "*.md")

    installed_hooks = _scan_dir(os.path.join(claude_dir, "hooks"), "*.py")
    installed_commands = _scan_dir(os.path.join(claude_dir, "commands"), "*.md")

    # Detect external plugin conflicts
    external_conflicts = _detect_external_conflicts(claude_dir)

    # Detect duplicate hook events
    duplicate_hooks = _detect_duplicate_hooks(claude_dir)

    # Check internal cohesion
    required_hooks = {
        "firewall.py", "secret-guard.py", "prompt-enhancer.py",
        "stop_dispatcher.py", "circuit-breaker.py", "session-start.py",
    }
    installed_hook_names = {os.path.basename(h) for h in installed_hooks}
    missing = required_hooks - installed_hook_names
    orphaned = [h for h in installed_hook_names
                if h.endswith(".py") and not h.startswith("_")
                and h not in {os.path.basename(s) for s in hooks}]

    gaps = []
    if missing:
        gaps.append(f"Missing required hooks: {', '.join(sorted(missing))}")
    if orphaned:
        gaps.append(f"Orphaned hooks (in install, not in source): {', '.join(sorted(orphaned))}")
    if external_conflicts:
        gaps.append(f"External conflicts: {len(external_conflicts)}")

    return {
        "status": "gaps" if gaps else "complete",
        "dependency_graph": {
            "commands": len(commands),
            "hooks": len(hooks),
            "agents": len(agents),
            "installed_hooks": len(installed_hooks),
            "installed_commands": len(installed_commands),
        },
        "external_conflicts": external_conflicts,
        "duplicate_hooks": duplicate_hooks,
        "orphaned_hooks": orphaned,
        "missing_hooks": sorted(missing),
        "gaps": gaps,
    }


def _scan_dir(path: str, pattern: str) -> list[str]:
    if not os.path.isdir(path):
        return []
    ext = pattern.lstrip("*")
    return [os.path.join(path, f) for f in os.listdir(path) if f.endswith(ext)]


def _detect_external_conflicts(claude_dir: str) -> list[dict[str, str]]:
    """Detect conflicts with Superpowers, OMC, OMX hook overrides."""
    conflicts = []
    hooks_dir = os.path.join(claude_dir, "hooks")
    if not os.path.isdir(hooks_dir):
        return conflicts

    # Check for non-OMG hooks on the same events
    foreign_markers = ["superpowers", "omc", "omx", "opencode-hooks"]
    for fname in os.listdir(hooks_dir):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(hooks_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                header = f.read(500).lower()
            for marker in foreign_markers:
                if marker in header:
                    conflicts.append({
                        "file": fname,
                        "source": marker,
                        "risk": "Hook event conflict — both OMG and external plugin register handlers",
                    })
        except OSError:
            continue

    return conflicts


def _detect_duplicate_hooks(claude_dir: str) -> list[dict[str, Any]]:
    """Check settings.json for duplicate hook event registrations."""
    duplicates = []
    settings_path = os.path.join(claude_dir, "settings.json")
    if not os.path.exists(settings_path):
        return duplicates

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return duplicates

    hooks = settings.get("hooks", {})
    for event_name, entries in hooks.items():
        if isinstance(entries, list) and len(entries) > 1:
            # Check for same command registered multiple times
            commands_seen: dict[str, int] = {}
            for entry in entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    if cmd:
                        commands_seen[cmd] = commands_seen.get(cmd, 0) + 1
            for cmd, count in commands_seen.items():
                if count > 1:
                    duplicates.append({
                        "event": event_name,
                        "command": cmd,
                        "count": count,
                    })

    return duplicates
