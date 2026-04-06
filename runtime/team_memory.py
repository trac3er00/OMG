from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROLES = ("admin", "developer", "viewer")
_READ_ONLY_ROLES = frozenset({"viewer"})


@dataclass
class TeamMemoryEntry:
    category: str
    data: dict[str, Any]
    author: str
    role: str
    entry_id: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            import hashlib

            self.entry_id = hashlib.sha256(
                f"{self.category}:{json.dumps(self.data)}:{time.time()}".encode()
            ).hexdigest()[:12]
        if not self.timestamp:
            from datetime import datetime, timezone

            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.entry_id,
            "category": self.category,
            "data": self.data,
            "author": self.author,
            "role": self.role,
            "timestamp": self.timestamp,
        }


class TeamMemory:
    def __init__(self, project_dir: str = "."):
        self._store_path = Path(project_dir) / ".omg" / "state" / "team-memory.jsonl"
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        category: str,
        data: dict[str, Any],
        author: str = "unknown",
        role: str = "developer",
    ) -> TeamMemoryEntry:
        if role in _READ_ONLY_ROLES:
            raise PermissionError(f"Role '{role}' has read-only access")
        try:
            from runtime.memory_schema import validate

            validate(category, data)
        except ImportError:
            pass
        entry = TeamMemoryEntry(category=category, data=data, author=author, role=role)
        with open(self._store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
        return entry

    def read(
        self,
        category: str | None = None,
        author: str | None = None,
        limit: int = 50,
    ) -> list[TeamMemoryEntry]:
        if not self._store_path.exists():
            return []
        entries = []
        for line in self._store_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                entries.append(
                    TeamMemoryEntry(
                        category=d.get("category", ""),
                        data=d.get("data", {}),
                        author=d.get("author", ""),
                        role=d.get("role", ""),
                        entry_id=d.get("id", ""),
                        timestamp=d.get("timestamp", ""),
                    )
                )
            except Exception:
                continue
        if category:
            entries = [e for e in entries if e.category == category]
        if author:
            entries = [e for e in entries if e.author == author]
        return entries[-limit:]

    def delete(self, entry_id: str, role: str = "developer") -> bool:
        if role != "admin":
            raise PermissionError(f"Role '{role}' cannot delete entries")
        if not self._store_path.exists():
            return False
        lines = [
            l
            for l in self._store_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        before = len(lines)
        new_lines = []
        for l in lines:
            try:
                if json.loads(l).get("id") != entry_id:
                    new_lines.append(l)
            except Exception:
                new_lines.append(l)
        self._store_path.write_text(
            "\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8"
        )
        return len(new_lines) < before
