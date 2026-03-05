"""FailureLearner — records agent failures and learns patterns to warn on similar future contexts."""
from __future__ import annotations

import json
import os
import re
from importlib import import_module
from typing import cast

from claude_experimental.memory.episodic import EpisodicMemory
from claude_experimental.memory.store import MemoryStore


class FailureLearner:
    """Records agent failures and learns patterns to warn on similar future contexts.

    Uses episodic memory to store failure records and FTS5 search to find
    similar past failures when new errors occur.  Warn-only: does not
    prevent dispatch or automatic avoidance.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.store: MemoryStore = MemoryStore(db_path=db_path) if db_path else MemoryStore()
        self.episodic: EpisodicMemory = EpisodicMemory(self.store)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_failure(
        self,
        context: str,
        error_type: str,
        error_message: str,
        stack_trace: str | None = None,
    ) -> int:
        """Record a failure for future pattern matching.

        Returns the memory ID of the stored failure record.
        """
        _require_memory_enabled()

        sanitized_trace: str | None = (
            self._sanitize_trace(stack_trace) if stack_trace else None
        )

        content = f"FAILURE: {error_type} | Context: {context} | Error: {error_message}"

        metadata: dict[str, object] = {
            "error_type": error_type,
            "context": context,
            "error_message": error_message,
            "sanitized_trace": sanitized_trace,
            "event_type": "failure",
        }

        return self.store.save(
            content=content,
            memory_type="episodic",
            importance=0.9,
            metadata=metadata,
        )

    def suggest_fix(
        self,
        error_type: str,
        context: str,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        """Find past failures matching this error type and context.

        Returns list of dicts with context, error_type, error_message,
        memory_id, and relevance score.
        """
        _require_memory_enabled()

        # FTS5 uses implicit AND; use OR for broader failure matching
        raw_terms = f"{error_type} {context}".split()
        query = " OR ".join(raw_terms)
        results = self.episodic.recall(
            query=query,
            limit=limit,
            event_type_filter="failure",
        )

        suggestions: list[dict[str, object]] = []
        for result in results:
            meta = _parse_metadata(result)
            suggestions.append({
                "context": str(meta.get("context", "")),
                "error_type": str(meta.get("error_type", "")),
                "error_message": str(meta.get("error_message", "")),
                "memory_id": result.get("id", 0),
                "relevance": float(cast(float, result.get("score", 0.0))),
            })

        return suggestions

    def get_failure_patterns(
        self,
        min_occurrences: int = 2,
    ) -> list[dict[str, object]]:
        """Find recurring failure patterns grouped by error type.

        Returns error types that have occurred at least *min_occurrences* times.
        """
        _require_memory_enabled()

        conn = self.store.connect()
        try:
            rows = conn.execute(
                "SELECT metadata FROM memories WHERE memory_type = 'episodic'"
            ).fetchall()

            counts: dict[str, int] = {}
            for row in rows:
                meta = _safe_parse_json(row["metadata"])
                if meta.get("event_type") != "failure":
                    continue
                error_type = str(meta.get("error_type", "unknown"))
                counts[error_type] = counts.get(error_type, 0) + 1

            return [
                {"error_type": error_type, "count": count}
                for error_type, count in sorted(counts.items())
                if count >= min_occurrences
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_trace(trace: str) -> str:
        """Remove full file paths and line numbers from stack traces."""
        sanitized = re.sub(
            r'File "([^"]+)"',
            lambda m: f'File "{os.path.basename(m.group(1))}"',
            trace,
        )
        return re.sub(r", line \d+", "", sanitized)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _require_memory_enabled() -> None:
    """Gate all public methods behind the experimental memory feature flag."""
    memory_module = import_module("claude_experimental.memory")
    require_enabled = getattr(memory_module, "_require_enabled", None)
    if callable(require_enabled):
        _ = require_enabled()
        return
    raise RuntimeError("claude_experimental.memory._require_enabled is unavailable")


def _parse_metadata(result: dict[str, object]) -> dict[str, object]:
    """Parse metadata from a recall result dict."""
    return _safe_parse_json(result.get("metadata"))


def _safe_parse_json(value: object) -> dict[str, object]:
    """Safely parse a JSON string or coerce a dict; returns empty dict on failure."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                parsed_dict = cast(dict[object, object], parsed)
                return {str(k): v for k, v in parsed_dict.items()}
        except json.JSONDecodeError:
            pass
        return {}
    if isinstance(value, dict):
        raw_dict = cast(dict[object, object], value)
        return {str(k): v for k, v in raw_dict.items()}
    return {}


__all__ = ["FailureLearner"]
