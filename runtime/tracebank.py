"""Structured trace capture for OMG routes and release evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import platform
import socket
from typing import Any
from uuid import uuid4


TRACEBANK_REL_PATH = Path(".omg") / "tracebank" / "events.jsonl"
TRACEBANK_EVIDENCE_LINKS_REL_PATH = Path(".omg") / "tracebank" / "evidence-links.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _executor() -> dict[str, str | int]:
    return {
        "user": getpass.getuser(),
        "pid": os.getpid(),
    }


def _environment() -> dict[str, str]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
    }


def record_trace(
    project_dir: str,
    *,
    trace_type: str,
    route: str,
    status: str,
    schema_version: int | None = None,
    plan: dict[str, Any] | None = None,
    patch: dict[str, Any] | None = None,
    verify: dict[str, Any] | None = None,
    failures: list[dict[str, Any]] | None = None,
    rejections: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace_id = f"trace-{uuid4().hex}"
    timestamp = _now()
    record: dict[str, Any] = {
        "schema": "TracebankRecord",
        "trace_id": trace_id,
        "timestamp": timestamp,
        "recorded_at": _now(),
        "executor": _executor(),
        "environment": _environment(),
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
    if schema_version is not None:
        record["schema_version"] = schema_version
    elif isinstance(metadata, dict) and metadata.get("schema_version") is not None:
        record["schema_version"] = metadata.get("schema_version")

    path = Path(project_dir) / TRACEBANK_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    record["path"] = TRACEBANK_REL_PATH.as_posix()
    return record


def link_evidence(
    project_dir: str,
    *,
    trace_id: str,
    evidence_path: str,
    schema_version: int | None = None,
) -> dict[str, Any]:
    link: dict[str, Any] = {
        "schema": "TraceEvidenceLink",
        "trace_id": trace_id,
        "evidence_path": evidence_path,
        "timestamp": _now(),
        "executor": _executor(),
        "environment": _environment(),
    }
    if schema_version is not None:
        link["schema_version"] = schema_version

    path = Path(project_dir) / TRACEBANK_EVIDENCE_LINKS_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(link, ensure_ascii=True) + "\n")

    link["path"] = TRACEBANK_EVIDENCE_LINKS_REL_PATH.as_posix()
    return link
