"""Structured trace capture for OMG routes and release evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


TRACEBANK_REL_PATH = Path(".omg") / "tracebank" / "events.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_trace(
    project_dir: str,
    *,
    trace_type: str,
    route: str,
    status: str,
    plan: dict[str, Any] | None = None,
    patch: dict[str, Any] | None = None,
    verify: dict[str, Any] | None = None,
    failures: list[dict[str, Any]] | None = None,
    rejections: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace_id = f"trace-{uuid4().hex}"
    record = {
        "schema": "TracebankRecord",
        "trace_id": trace_id,
        "recorded_at": _now(),
        "trace_type": trace_type,
        "route": route,
        "status": status,
        "plan": plan or {},
        "patch": patch or {},
        "verify": verify or {},
        "failures": failures or [],
        "rejections": rejections or [],
        "metadata": metadata or {},
    }

    path = Path(project_dir) / TRACEBANK_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    record["path"] = TRACEBANK_REL_PATH.as_posix()
    return record
