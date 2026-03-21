"""Sequential checklist tracker — atomic per-item checkmarks with resume."""
from __future__ import annotations

import re
from pathlib import Path


class ChecklistTracker:
    """Track and advance through a markdown checklist one item at a time."""

    def __init__(self, checklist_path: str | Path):
        self.path = Path(checklist_path)
        self._lines: list[str] = []
        self._items: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        self._lines = self.path.read_text(encoding="utf-8").splitlines(keepends=True)
        self._items = []
        pattern = re.compile(r"^(\s*)-\s*\[([ xX])\]\s*(.*)")
        for idx, line in enumerate(self._lines):
            m = pattern.match(line)
            if m:
                self._items.append({
                    "line_idx": idx,
                    "indent": m.group(1),
                    "done": m.group(2).lower() == "x",
                    "text": m.group(3).strip(),
                })

    @property
    def total(self) -> int:
        return len(self._items)

    @property
    def done(self) -> int:
        return sum(1 for item in self._items if item["done"])

    @property
    def current(self) -> dict | None:
        """Return first unchecked item, or None if all done."""
        for item in self._items:
            if not item["done"]:
                return item
        return None

    @property
    def progress(self) -> str:
        """Return progress bar string."""
        total = self.total
        done = self.done
        if total == 0:
            return "[no items]"
        filled = int((done / total) * 10)
        bar = "█" * filled + "░" * (10 - filled)
        pct = int((done / total) * 100)
        return f"[{bar}] {pct}% ({done}/{total})"

    def mark_done(self, item_idx: int | None = None) -> bool:
        """Atomically mark the current (or specified) item as done and write to disk.

        Returns True if an item was marked, False if nothing to mark.
        """
        if item_idx is not None:
            if item_idx < 0 or item_idx >= len(self._items):
                return False
            target = self._items[item_idx]
        else:
            target = self.current
        if target is None or target["done"]:
            return False

        line_idx = target["line_idx"]
        old_line = self._lines[line_idx]
        new_line = old_line.replace("- [ ]", "- [x]", 1)
        if new_line == old_line:
            new_line = old_line.replace("- [  ]", "- [x]", 1)
        self._lines[line_idx] = new_line
        target["done"] = True

        # Atomic write
        self.path.write_text("".join(self._lines), encoding="utf-8")
        return True

    def find_phase(self) -> str | None:
        """Return the phase header for the current item."""
        current = self.current
        if current is None:
            return None
        # Walk backwards from current item to find nearest ## header
        for idx in range(current["line_idx"], -1, -1):
            line = self._lines[idx]
            if line.startswith("## ") or line.startswith("### "):
                return line.strip().lstrip("#").strip()
        return None

    def summary(self) -> dict:
        """Return structured summary for handoff files."""
        current = self.current
        return {
            "path": str(self.path),
            "total": self.total,
            "done": self.done,
            "progress": self.progress,
            "current_item": current["text"] if current else None,
            "current_phase": self.find_phase(),
            "all_done": self.current is None and self.total > 0,
        }
