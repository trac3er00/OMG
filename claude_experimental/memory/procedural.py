"""ProceduralMemory — how-to knowledge: strategies, decompositions, workflows.

Stores task decomposition procedures as structured JSON in SQLite via MemoryStore.
Each procedure tracks its success rate using exponential moving average,
enabling identification of low-confidence procedures for revision.
"""
from __future__ import annotations

from importlib import import_module
import json
from typing import cast

from claude_experimental.memory.store import MemoryStore

_SCHEMA_VERSION = 1
_EMA_ALPHA = 0.2  # Weight for new observations: new_rate = 0.8*old + 0.2*new


class ProceduralMemory:
    """Manages how-to knowledge: strategies, decompositions, workflows.

    Procedures are stored as structured JSON with success rate tracking
    via exponential moving average.
    """

    def __init__(self, store: MemoryStore | None = None):
        self.store: MemoryStore = store or MemoryStore()

    def store_procedure(
        self,
        task_type: str,
        steps: list[str],
        prerequisites: list[str] | None = None,
        applicable_context: str | None = None,
        success_rate: float = 0.5,
    ) -> int:
        """Store a new procedure. Returns the procedure_id (memory row ID)."""
        _require_memory_enabled()

        payload: dict[str, object] = {
            "task_type": task_type.strip(),
            "steps": list(steps),
            "prerequisites": list(prerequisites) if prerequisites else [],
            "applicable_context": applicable_context or "",
            "success_rate": max(0.0, min(1.0, success_rate)),
            "use_count": 0,
            "schema_version": _SCHEMA_VERSION,
        }
        content = json.dumps(payload, sort_keys=True)

        return self.store.save(
            content=content,
            memory_type="procedural",
            importance=max(0.3, success_rate),
        )

    def find_procedure(
        self,
        task_description: str,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        """Find procedures matching a task description via FTS search.

        Returns list of procedure dicts sorted by relevance.
        """
        _require_memory_enabled()

        fts_query = _to_fts_query(task_description)
        results = self.store.search(
            query=fts_query,
            limit=max(limit, 1),
            memory_type="procedural",
        )

        procedures: list[dict[str, object]] = []
        for item in results:
            memory = dict(item)
            procedure = _parse_procedure(memory)
            if procedure is not None:
                procedures.append(procedure)

        return procedures[:limit]

    def record_outcome(self, procedure_id: int, success: bool) -> None:
        """Update a procedure's success rate using exponential moving average.

        Formula: new_rate = 0.8 * old_rate + 0.2 * (1.0 if success else 0.0)
        Also increments use_count.
        """
        _require_memory_enabled()

        memory = self.store.get_by_id(procedure_id)
        if memory is None:
            raise ValueError(f"Procedure not found: {procedure_id}")

        content_raw = memory.get("content", "{}")
        if not isinstance(content_raw, str):
            raise ValueError(f"Corrupted procedure data for id={procedure_id}")

        try:
            parsed = cast(dict[str, object], json.loads(content_raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupted procedure JSON for id={procedure_id}") from exc

        old_rate = float(cast(int | float | str, parsed.get("success_rate", 0.5)))
        observation = 1.0 if success else 0.0
        new_rate = (1.0 - _EMA_ALPHA) * old_rate + _EMA_ALPHA * observation
        new_rate = max(0.0, min(1.0, new_rate))

        parsed["success_rate"] = new_rate
        parsed["use_count"] = int(cast(int | float | str, parsed.get("use_count", 0))) + 1

        updated_content = json.dumps(parsed, sort_keys=True)

        # Direct UPDATE via connection — FTS triggers handle sync automatically
        conn = self.store.connect()
        try:
            _ = conn.execute(
                "UPDATE memories SET content = ?, importance = ? WHERE id = ?",
                (updated_content, max(0.3, new_rate), procedure_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_low_success_procedures(
        self, threshold: float = 0.3,
    ) -> list[dict[str, object]]:
        """Return procedures with success_rate below threshold, flagged for revision."""
        _require_memory_enabled()

        conn = self.store.connect()
        try:
            rows = conn.execute(
                "SELECT id, content FROM memories WHERE memory_type = ?",
                ("procedural",),
            ).fetchall()
        finally:
            conn.close()

        flagged: list[dict[str, object]] = []
        for row in rows:
            memory_id = row["id"]
            content_raw = row["content"]
            if not isinstance(content_raw, str):
                continue

            try:
                parsed = cast(dict[str, object], json.loads(content_raw))
            except json.JSONDecodeError:
                continue

            rate = float(cast(int | float | str, parsed.get("success_rate", 0.5)))
            if rate < threshold:
                flagged.append({
                    "id": memory_id,
                    "task_type": parsed.get("task_type", ""),
                    "steps": parsed.get("steps", []),
                    "prerequisites": parsed.get("prerequisites", []),
                    "applicable_context": parsed.get("applicable_context", ""),
                    "success_rate": rate,
                    "use_count": parsed.get("use_count", 0),
                })

        return flagged


def _require_memory_enabled() -> None:
    """Enforce feature flag gating via dynamic import."""
    memory_module = import_module("claude_experimental.memory")
    require_enabled = getattr(memory_module, "_require_enabled", None)
    if callable(require_enabled):
        _ = require_enabled()
        return
    raise RuntimeError("claude_experimental.memory._require_enabled is unavailable")


def _to_fts_query(task_description: str) -> str:
    """Build FTS5 OR-prefix query for fuzzy task matching.

    Transforms 'implement authentication' → 'implement* OR authentication*'
    so FTS5 can match partial tokens like 'implementation' from 'auth_implementation'.
    """
    tokens: list[str] = []
    for word in task_description.split():
        cleaned = "".join(c for c in word if c.isalnum())
        if cleaned:
            tokens.append(cleaned)
    if not tokens:
        return task_description
    return " OR ".join(f"{t}*" for t in tokens)


def _parse_procedure(memory: dict[str, object]) -> dict[str, object] | None:
    """Extract structured procedure dict from a raw memory row."""
    content_raw = memory.get("content", "{}")
    if not isinstance(content_raw, str):
        return None
    try:
        parsed = cast(dict[str, object], json.loads(content_raw))
    except json.JSONDecodeError:
        return None

    return {
        "id": memory.get("id"),
        "task_type": parsed.get("task_type", ""),
        "steps": parsed.get("steps", []),
        "prerequisites": parsed.get("prerequisites", []),
        "applicable_context": parsed.get("applicable_context", ""),
        "success_rate": parsed.get("success_rate", 0.5),
        "use_count": parsed.get("use_count", 0),
    }
