from __future__ import annotations

from importlib import import_module
import json
from typing import cast

from claude_experimental.memory.store import MemoryStore

_EVENT_TYPES = {"success", "failure", "decision", "discovery"}


class EpisodicMemory:
    def __init__(self, store: MemoryStore | None = None):
        self.store: MemoryStore = store or MemoryStore()

    def record(
        self,
        event_type: str,
        context: object,
        outcome: object,
        session_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> int:
        _require_memory_enabled()

        normalized_event_type = event_type.strip().lower()
        if normalized_event_type not in _EVENT_TYPES:
            allowed = ", ".join(sorted(_EVENT_TYPES))
            raise ValueError(f"Invalid event_type '{event_type}'. Allowed values: {allowed}")

        importance = self._importance_for(normalized_event_type, outcome, metadata)
        payload = {
            "event_type": normalized_event_type,
            "session_id": session_id,
            "context": context,
            "outcome": outcome,
        }
        content = self._to_text(payload)

        store_metadata: dict[str, object] = {
            "event_type": normalized_event_type,
            "session_id": session_id,
            "context": context,
            "outcome": outcome,
        }
        if metadata:
            store_metadata.update(metadata)

        return self.store.save(
            content=content,
            memory_type="episodic",
            importance=importance,
            metadata=store_metadata,
        )

    def recall(
        self,
        query: str,
        limit: int = 5,
        temperature: float = 0.3,
        event_type_filter: str | None = None,
    ) -> list[dict[str, object]]:
        _require_memory_enabled()

        clamped_temperature = max(0.0, min(1.0, temperature))
        min_score = 1.0 - clamped_temperature
        normalized_filter = event_type_filter.strip().lower() if event_type_filter else None
        if normalized_filter and normalized_filter not in _EVENT_TYPES:
            allowed = ", ".join(sorted(_EVENT_TYPES))
            raise ValueError(
                f"Invalid event_type_filter '{event_type_filter}'. Allowed values: {allowed}"
            )

        base_results = self.store.search(
            query=query,
            limit=max(limit, 1),
            memory_type="episodic",
        )

        filtered: list[dict[str, object]] = []
        total = len(base_results)
        for index, item in enumerate(base_results):
            memory = dict(item)
            metadata_raw = memory.get("metadata")
            if isinstance(metadata_raw, str):
                parsed_json: object
                try:
                    parsed_json = cast(object, json.loads(metadata_raw))
                except json.JSONDecodeError:
                    parsed_json = cast(object, {})
                metadata = _coerce_object_dict(parsed_json)
            else:
                metadata = _coerce_object_dict(metadata_raw)

            event_type = str(metadata.get("event_type", "")).strip().lower()
            if normalized_filter and event_type != normalized_filter:
                continue

            relevance = self._relevance(memory, index, total)
            memory["score"] = relevance
            if relevance >= min_score:
                filtered.append(memory)
                if len(filtered) >= limit:
                    break

        return filtered

    @staticmethod
    def _importance_for(
        event_type: str,
        outcome: object,
        metadata: dict[str, object] | None,
    ) -> float:
        if event_type == "success":
            return 0.7
        if event_type == "failure" and EpisodicMemory._has_lessons(outcome, metadata):
            return 0.8
        return 0.3

    @staticmethod
    def _has_lessons(outcome: object, metadata: dict[str, object] | None) -> bool:
        if metadata:
            if _contains_lesson_signal(metadata.get("lessons")):
                return True

        outcome_dict = _coerce_object_dict(outcome)
        if _contains_lesson_signal(outcome_dict.get("lessons")):
            return True

        outcome_text = EpisodicMemory._to_text(outcome).lower()
        return "lesson" in outcome_text or "learned" in outcome_text

    @staticmethod
    def _to_text(value: object) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, sort_keys=True, default=str)

    @staticmethod
    def _relevance(memory: dict[str, object], index: int, total: int) -> float:
        if total <= 1:
            rank_relevance = 1.0
        else:
            rank_relevance = max(0.0, min(1.0, 1.0 - (index / (total - 1))))

        score = memory.get("score")
        if isinstance(score, (int, float)):
            return max(0.0, min(1.0, float(score)))

        return rank_relevance


def _require_memory_enabled() -> None:
    memory_module = import_module("claude_experimental.memory")
    require_enabled = getattr(memory_module, "_require_enabled", None)
    if callable(require_enabled):
        _ = require_enabled()
        return
    raise RuntimeError("claude_experimental.memory._require_enabled is unavailable")


def _coerce_object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    value_dict = cast(dict[object, object], value)
    return {str(key): item for key, item in value_dict.items()}


def _contains_lesson_signal(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        for item in cast(list[object], value):
            if _contains_lesson_signal(item):
                return True
        return False
    if isinstance(value, tuple):
        for item in cast(tuple[object, ...], value):
            if _contains_lesson_signal(item):
                return True
        return False
    if isinstance(value, set):
        for item in cast(set[object], value):
            if _contains_lesson_signal(item):
                return True
        return False
    if isinstance(value, dict):
        value_dict = cast(dict[object, object], value)
        return _contains_lesson_signal(list(value_dict.values()))
    return False
