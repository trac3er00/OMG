"""Replayable incident pack generation."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_incident_pack(
    project_dir: str,
    *,
    title: str,
    failing_tests: list[str],
    logs: list[str],
    diff_summary: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    incident_id = f"incident-{uuid4().hex}"
    payload = {
        "schema": "IncidentReplayPack",
        "incident_id": incident_id,
        "title": title,
        "generated_at": _now(),
        "trace_id": trace_id or "",
        "failing_tests": failing_tests,
        "logs": logs,
        "diff_summary": diff_summary,
        "reproduction_steps": [
            "Replay the failing tests.",
            "Inspect the attached logs.",
            "Validate the diff summary before patching.",
        ],
        "regression_guards": failing_tests,
    }

    rel_path = Path(".omg") / "incidents" / f"{incident_id}.json"
    path = Path(project_dir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["path"] = rel_path.as_posix()
    return payload
