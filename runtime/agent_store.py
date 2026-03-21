"""Self-updating agent store — git-backed agent registry.

Manages custom agent definitions with versioning, auto-update from
remote git repositories, and local override support.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


STORE_DIR = ".omg/agents"
STORE_INDEX = ".omg/agents/.index.json"
REMOTE_DEFAULT = "https://github.com/trac3r00/OMG.git"
AGENTS_SUBPATH = "agents"


@dataclass
class AgentEntry:
    name: str
    source: str  # "builtin" | "custom" | "remote"
    path: str
    version: str = ""
    updated_at: str = ""
    remote_url: str = ""
    auto_update: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentStore:
    """Git-backed agent store with local overrides."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.store_dir = os.path.join(project_dir, STORE_DIR)
        self.index_path = os.path.join(project_dir, STORE_INDEX)

    def init(self) -> None:
        """Initialize the store directory."""
        os.makedirs(self.store_dir, exist_ok=True)
        if not os.path.exists(self.index_path):
            self._write_index([])

    def list_agents(self) -> list[AgentEntry]:
        """List all agents in the store."""
        entries = self._read_index()
        # Also scan for .md files not in index
        if os.path.isdir(self.store_dir):
            indexed_paths = {e.path for e in entries}
            for fname in sorted(os.listdir(self.store_dir)):
                if fname.endswith(".md") and fname != ".index.json":
                    rel_path = os.path.join(STORE_DIR, fname)
                    if rel_path not in indexed_paths:
                        entries.append(AgentEntry(
                            name=fname.replace(".md", ""),
                            source="custom",
                            path=rel_path,
                        ))
        return entries

    def add_agent(self, name: str, content: str, source: str = "custom") -> AgentEntry:
        """Add or update an agent definition."""
        self.init()
        fname = f"{name}.md" if not name.endswith(".md") else name
        agent_path = os.path.join(self.store_dir, fname)
        with open(agent_path, "w", encoding="utf-8") as f:
            f.write(content)

        entry = AgentEntry(
            name=name.replace(".md", ""),
            source=source,
            path=os.path.join(STORE_DIR, fname),
            updated_at=_iso_now(),
        )

        entries = self._read_index()
        entries = [e for e in entries if e.name != entry.name]
        entries.append(entry)
        self._write_index(entries)
        return entry

    def remove_agent(self, name: str) -> bool:
        """Remove an agent from the store."""
        entries = self._read_index()
        found = [e for e in entries if e.name == name]
        if not found:
            return False
        for entry in found:
            full_path = os.path.join(self.project_dir, entry.path)
            if os.path.exists(full_path):
                os.remove(full_path)
        entries = [e for e in entries if e.name != name]
        self._write_index(entries)
        return True

    def sync_from_remote(self, remote_url: str | None = None) -> dict[str, Any]:
        """Sync agents from a remote git repository.

        Clones/pulls the remote repo and copies agent .md files into the store.
        Returns sync result with counts.
        """
        url = remote_url or REMOTE_DEFAULT
        self.init()
        cache_dir = os.path.join(self.project_dir, ".omg", ".agent-store-cache")

        try:
            if os.path.isdir(cache_dir):
                subprocess.run(
                    ["git", "-C", cache_dir, "pull", "--ff-only"],
                    capture_output=True, timeout=30,
                )
            else:
                subprocess.run(
                    ["git", "clone", "--depth", "1", url, cache_dir],
                    capture_output=True, timeout=60,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {"status": "error", "reason": "git operation failed"}

        agents_src = os.path.join(cache_dir, AGENTS_SUBPATH)
        if not os.path.isdir(agents_src):
            return {"status": "error", "reason": f"no {AGENTS_SUBPATH}/ in remote"}

        added = 0
        updated = 0
        for fname in os.listdir(agents_src):
            if not fname.endswith(".md"):
                continue
            src = os.path.join(agents_src, fname)
            dst = os.path.join(self.store_dir, fname)
            if os.path.exists(dst):
                updated += 1
            else:
                added += 1
            shutil.copy2(src, dst)

        return {"status": "ok", "added": added, "updated": updated, "remote": url}

    def _read_index(self) -> list[AgentEntry]:
        if not os.path.exists(self.index_path):
            return []
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [AgentEntry(**e) for e in data if isinstance(e, dict)]
        except (json.JSONDecodeError, OSError, TypeError):
            return []

    def _write_index(self, entries: list[AgentEntry]) -> None:
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in entries], f, indent=2)


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
