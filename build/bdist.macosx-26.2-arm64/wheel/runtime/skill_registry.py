from __future__ import annotations

import json
import os
from pathlib import Path


def compact_registry(all_skills: list[str], used: list[str]) -> dict[str, object]:
    normalized_all = _normalize_names(all_skills)
    normalized_used = _normalize_names(used)

    active = [name for name in normalized_used if name in normalized_all]
    pruned = [name for name in normalized_all if name not in set(active)]
    summary_metadata = {name: _summary_snippet(name) for name in active}

    payload: dict[str, object] = {
        "active": active,
        "pruned": pruned,
        "summary_metadata": summary_metadata,
    }
    _persist_compact_registry(_project_dir(), payload)
    return payload


def _normalize_names(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _summary_snippet(skill_name: str) -> str:
    cleaned = skill_name.split("/")[-1].replace("-", " ").replace("_", " ").strip()
    return cleaned[:80] if cleaned else skill_name[:80]


def _project_dir(project_dir: str | None = None) -> Path:
    if project_dir:
        return Path(project_dir)
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _persist_compact_registry(project_dir: Path, payload: dict[str, object]) -> None:
    output_path = project_dir / ".omg" / "state" / "skill_registry" / "compact.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    _ = temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    _ = os.replace(temp_path, output_path)
