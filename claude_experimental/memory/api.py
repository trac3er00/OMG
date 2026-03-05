from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
import re
import sqlite3
from typing import cast

from claude_experimental.memory.episodic import EpisodicMemory
from claude_experimental.memory.procedural import ProceduralMemory
from claude_experimental.memory.semantic import SemanticMemory
from claude_experimental.memory.store import MemoryStore


_PROCEDURAL_HINTS = ("step ", "steps:")
_EPISODIC_HINTS = ("event:", "outcome:", "fixed", "resolved")
_NUMBERED_LIST_PATTERN = re.compile(r"(^|\n)\s*\d+[.)]\s+")
_STEP_EXTRACT_PATTERN = re.compile(r"step\s*\d+\s*:\s*", re.IGNORECASE)


@dataclass
class RetrievedMemory:
    source_type: str
    relevance_score: float
    content: str
    memory_id: int | None
    metadata: dict[str, object]


def remember(
    content: str,
    importance: float = 0.5,
    memory_type: str = "auto",
    scope: str = "session",
    metadata: dict[str, object] | None = None,
) -> int:
    _require_memory_enabled()

    normalized_type = memory_type.strip().lower()
    selected_type = _detect_memory_type(content) if normalized_type == "auto" else normalized_type
    if selected_type not in {"semantic", "episodic", "procedural"}:
        raise ValueError("memory_type must be one of: auto, semantic, episodic, procedural")

    store = MemoryStore(scope=scope)
    safe_importance = max(0.0, min(1.0, importance))

    if selected_type == "procedural":
        procedural = ProceduralMemory(store)
        steps = _extract_steps(content)
        task_type = _task_type_from(content, metadata)
        return procedural.store_procedure(
            task_type=task_type,
            steps=steps,
            success_rate=safe_importance,
        )

    if selected_type == "episodic":
        episodic = EpisodicMemory(store)
        event_type = _event_type_from(content)
        store_metadata: dict[str, object] = dict(metadata or {})
        _ = store_metadata.setdefault("importance", safe_importance)
        session_value = store_metadata.get("session_id")
        session_id = str(session_value) if isinstance(session_value, (int, float, str)) else None
        return episodic.record(
            event_type=event_type,
            context={"content": content},
            outcome=content,
            session_id=session_id,
            metadata=store_metadata,
        )

    semantic = SemanticMemory(store)
    return semantic.store_fact(
        content=content,
        importance=safe_importance,
        scope=scope,
        metadata=metadata,
    )


def recall(
    query: str,
    limit: int = 5,
    temperature: float = 0.3,
    memory_types: list[str] | None = None,
    scope_filter: str | list[str] | None = None,
    min_relevance: float = 0.5,
) -> list[RetrievedMemory]:
    _require_memory_enabled()

    clamped_limit = max(1, limit)
    clamped_relevance = max(0.0, min(1.0, min_relevance))
    allowed_types = {"semantic", "episodic", "procedural"}
    selected_types = {t.strip().lower() for t in (memory_types or list(allowed_types))}
    invalid = sorted(t for t in selected_types if t not in allowed_types)
    if invalid:
        raise ValueError(f"Invalid memory_types: {', '.join(invalid)}")

    scope_values = _normalize_scopes(scope_filter)
    unified: list[RetrievedMemory] = []

    scopes_to_search = scope_values or ["project", "session", "user"]
    seen_keys: set[tuple[str, int | None, str]] = set()
    per_type_limit = max(clamped_limit * 2, 5)

    for scope in scopes_to_search:
        store = MemoryStore(scope=scope)

        if "semantic" in selected_types:
            semantic = SemanticMemory(store)
            semantic_rows = semantic.search(query=query, limit=per_type_limit, min_score=0.0)
            for row in semantic_rows:
                relevance = _coerce_score(row.get("score"), fallback=0.0)
                if relevance < clamped_relevance:
                    continue
                memory_id = _coerce_int(row.get("id"))
                content = str(row.get("content", ""))
                item = RetrievedMemory(
                    source_type="semantic",
                    relevance_score=relevance,
                    content=content,
                    memory_id=memory_id,
                    metadata=_extract_metadata(row),
                )
                _append_unique(unified, seen_keys, item)

        if "episodic" in selected_types:
            episodic = EpisodicMemory(store)
            episodic_rows = episodic.recall(
                query=query,
                limit=per_type_limit,
                temperature=temperature,
                event_type_filter=None,
            )
            for row in episodic_rows:
                relevance = _coerce_score(row.get("score"), fallback=0.0)
                if relevance < clamped_relevance:
                    continue
                memory_id = _coerce_int(row.get("id"))
                content = str(row.get("content", ""))
                item = RetrievedMemory(
                    source_type="episodic",
                    relevance_score=relevance,
                    content=content,
                    memory_id=memory_id,
                    metadata=_extract_metadata(row),
                )
                _append_unique(unified, seen_keys, item)

        if "procedural" in selected_types:
            procedural = ProceduralMemory(store)
            procedures = procedural.find_procedure(task_description=query, limit=per_type_limit)
            total = len(procedures)
            for idx, proc in enumerate(procedures):
                rank_score = _rank_score(idx, total)
                success_rate = _coerce_score(proc.get("success_rate"), fallback=0.5)
                relevance = (rank_score * 0.6) + (success_rate * 0.4)
                if relevance < clamped_relevance:
                    continue
                memory_id = _coerce_int(proc.get("id"))
                steps = proc.get("steps", [])
                steps_text = "\n".join(f"- {step}" for step in _as_str_list(steps))
                content = str(proc.get("task_type", "procedural"))
                if steps_text:
                    content = f"{content}\n{steps_text}"
                item = RetrievedMemory(
                    source_type="procedural",
                    relevance_score=max(0.0, min(1.0, relevance)),
                    content=content,
                    memory_id=memory_id,
                    metadata={
                        "task_type": proc.get("task_type", ""),
                        "steps": _as_str_list(steps),
                        "prerequisites": _as_str_list(proc.get("prerequisites", [])),
                        "applicable_context": str(proc.get("applicable_context", "")),
                        "success_rate": success_rate,
                        "use_count": _coerce_int(proc.get("use_count")) or 0,
                        "scope": scope,
                    },
                )
                _append_unique(unified, seen_keys, item)

    unified.sort(key=lambda item: item.relevance_score, reverse=True)
    return unified[:clamped_limit]


def memory_check(
    scope: str = "project",
    repair: bool = True,
    compact: bool = False,
) -> dict[str, object]:
    _require_memory_enabled()

    store = MemoryStore(scope=scope)
    conn = store.connect()
    try:
        integrity_result = cast(
            sqlite3.Row | None,
            conn.execute("PRAGMA integrity_check").fetchone(),
        )
        integrity = (
            str(cast(object, integrity_result[0]))
            if integrity_result is not None
            else "unknown"
        )

        repaired = False
        repair_error: str | None = None
        if integrity != "ok" and repair:
            try:
                _ = conn.execute("REINDEX")
                _ = conn.execute("VACUUM")
                conn.commit()
                post_repair = cast(
                    sqlite3.Row | None,
                    conn.execute("PRAGMA integrity_check").fetchone(),
                )
                integrity = (
                    str(cast(object, post_repair[0]))
                    if post_repair is not None
                    else integrity
                )
                repaired = True
            except sqlite3.DatabaseError as exc:
                repair_error = str(exc)

        if compact:
            _ = conn.execute("VACUUM")
            conn.commit()

        total_row = cast(
            sqlite3.Row | None,
            conn.execute("SELECT COUNT(*) FROM memories").fetchone(),
        )
        total_memories = (
            int(cast(int | float | str, total_row[0]))
            if total_row is not None
            else 0
        )

        by_type_rows = cast(
            list[sqlite3.Row],
            conn.execute(
                "SELECT memory_type, COUNT(*) AS count FROM memories GROUP BY memory_type"
            ).fetchall(),
        )
        memories_by_type = {
            str(cast(object, row[0])): int(cast(int | float | str, row[1]))
            for row in by_type_rows
        }

        by_scope_rows = cast(
            list[sqlite3.Row],
            conn.execute(
                "SELECT scope, COUNT(*) AS count FROM memories GROUP BY scope"
            ).fetchall(),
        )
        memories_by_scope = {
            str(cast(object, row[0])): int(cast(int | float | str, row[1]))
            for row in by_scope_rows
        }

        return {
            "scope": scope,
            "db_path": store.db_path,
            "integrity": integrity,
            "healthy": integrity == "ok",
            "repair_attempted": repair,
            "repaired": repaired,
            "repair_error": repair_error,
            "compacted": compact,
            "schema_version": store.get_schema_version(),
            "journal_mode": store.pragma("journal_mode"),
            "total_memories": total_memories,
            "memories_by_type": memories_by_type,
            "memories_by_scope": memories_by_scope,
        }
    finally:
        conn.close()


def _detect_memory_type(content: str) -> str:
    lowered = content.lower()
    if any(hint in lowered for hint in _PROCEDURAL_HINTS) or _NUMBERED_LIST_PATTERN.search(content):
        return "procedural"
    if any(hint in lowered for hint in _EPISODIC_HINTS):
        return "episodic"
    return "semantic"


def _extract_steps(content: str) -> list[str]:
    normalized = content.replace("\r\n", "\n").strip()
    if not normalized:
        return ["Review context", "Apply change", "Verify outcome"]

    numbered_lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        matched = re.match(r"^\d+[.)]\s+(.*)$", line)
        if matched:
            numbered_lines.append(matched.group(1).strip())
    if numbered_lines:
        return numbered_lines

    if _STEP_EXTRACT_PATTERN.search(normalized):
        parts = [part.strip(" ,;\n") for part in _STEP_EXTRACT_PATTERN.split(normalized) if part.strip()]
        if parts:
            return parts

    if "steps:" in normalized.lower():
        trailing = normalized.split(":", 1)[1] if ":" in normalized else normalized
        step_parts = [part.strip() for part in trailing.split(",") if part.strip()]
        if step_parts:
            return step_parts

    sentences = [segment.strip() for segment in re.split(r"[.;]\s*", normalized) if segment.strip()]
    return sentences[:8] if sentences else [normalized]


def _task_type_from(content: str, metadata: dict[str, object] | None) -> str:
    if metadata and isinstance(metadata.get("task_type"), str):
        task_type = str(metadata["task_type"]).strip()
        if task_type:
            return task_type
    first_line = content.strip().splitlines()[0] if content.strip() else "general-task"
    task_type = re.sub(r"\s+", "-", first_line.lower()).strip("-")
    return task_type[:80] or "general-task"


def _event_type_from(content: str) -> str:
    lowered = content.lower()
    if any(token in lowered for token in ("fixed", "resolved", "success", "passed")):
        return "success"
    if any(token in lowered for token in ("failed", "failure", "error", "broken")):
        return "failure"
    if "decid" in lowered:
        return "decision"
    return "discovery"


def _normalize_scopes(scope_filter: str | list[str] | None) -> list[str]:
    allowed = {"session", "project", "user"}
    if scope_filter is None:
        return []
    raw_values = [scope_filter] if isinstance(scope_filter, str) else list(scope_filter)
    normalized: list[str] = []
    for value in raw_values:
        item = str(value).strip().lower()
        if item not in allowed:
            raise ValueError("scope_filter must contain only: session, project, user")
        if item not in normalized:
            normalized.append(item)
    return normalized


def _extract_metadata(row: dict[str, object]) -> dict[str, object]:
    metadata_raw = row.get("metadata")
    metadata: dict[str, object] = {}
    if isinstance(metadata_raw, str):
        try:
            parsed = cast(object, json.loads(metadata_raw))
            if isinstance(parsed, dict):
                parsed_dict = cast(dict[object, object], parsed)
                metadata = {str(key): value for key, value in parsed_dict.items()}
        except json.JSONDecodeError:
            metadata = {}
    elif isinstance(metadata_raw, dict):
        metadata_dict = cast(dict[object, object], metadata_raw)
        metadata = {str(key): value for key, value in metadata_dict.items()}

    if "scope" in row:
        scope_value = row.get("scope")
        if scope_value is not None:
            _ = metadata.setdefault("scope", scope_value)
    return metadata


def _append_unique(
    target: list[RetrievedMemory],
    seen_keys: set[tuple[str, int | None, str]],
    item: RetrievedMemory,
) -> None:
    key = (item.source_type, item.memory_id, item.content)
    if key in seen_keys:
        return
    seen_keys.add(key)
    target.append(item)


def _coerce_score(value: object, fallback: float) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    try:
        return max(0.0, min(1.0, float(str(value))))
    except (TypeError, ValueError):
        return fallback


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _rank_score(index: int, total: int) -> float:
    if total <= 1:
        return 1.0
    return max(0.0, min(1.0, 1.0 - (index / (total - 1))))


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        values = cast(list[object], value)
        return [str(item) for item in values]
    if isinstance(value, tuple):
        values = cast(tuple[object, ...], value)
        return [str(item) for item in values]
    return []


__all__ = ["RetrievedMemory", "remember", "recall", "memory_check"]


def _require_memory_enabled() -> None:
    memory_module = import_module("claude_experimental.memory")
    require_enabled = getattr(memory_module, "_require_enabled", None)
    if callable(require_enabled):
        _ = require_enabled()
        return
    raise RuntimeError("claude_experimental.memory._require_enabled is unavailable")
