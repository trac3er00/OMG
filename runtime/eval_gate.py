"""Reproducible evaluation results for release gating."""
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


EVAL_GATE_LATEST_REL_PATH = Path(".omg") / "evals" / "latest.json"
EVAL_GATE_HISTORY_REL_PATH = Path(".omg") / "evals" / "history.jsonl"
EVAL_GATE_TRACE_LINKS_REL_PATH = Path(".omg") / "evals" / "trace-links.jsonl"


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


def evaluate_trace(
    project_dir: str,
    *,
    trace_id: str,
    suites: list[str],
    metrics: dict[str, float],
    lineage: dict[str, Any] | None = None,
    regression_threshold: float = 0.95,
) -> dict[str, Any]:
    eval_id = f"eval-{uuid4().hex}"
    scorecard = {name: float(metrics.get(name, 0.0)) for name in suites}
    regressed = any(score < regression_threshold for score in scorecard.values())
    result = {
        "schema": "EvalGateResult",
        "eval_id": eval_id,
        "trace_id": trace_id,
        "lineage": lineage or {},
        "evaluated_at": _now(),
        "timestamp": _now(),
        "executor": _executor(),
        "environment": _environment(),
        "status": "fail" if regressed else "ok",
        "suites": suites,
        "metrics": scorecard,
        "summary": {
            "regressed": regressed,
            "regression_threshold": regression_threshold,
        },
    }

    latest_path = Path(project_dir) / EVAL_GATE_LATEST_REL_PATH
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    _ = latest_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    _ = link_trace(project_dir, eval_id=eval_id, trace_id=trace_id)

    history_path = Path(project_dir) / EVAL_GATE_HISTORY_REL_PATH
    with history_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(result, ensure_ascii=True) + "\n")

    result["path"] = EVAL_GATE_LATEST_REL_PATH.as_posix()
    return result


def link_trace(project_dir: str, *, eval_id: str, trace_id: str) -> dict[str, Any]:
    link = {
        "schema": "EvalTraceLink",
        "eval_id": eval_id,
        "trace_id": trace_id,
        "timestamp": _now(),
        "executor": _executor(),
        "environment": _environment(),
    }
    path = Path(project_dir) / EVAL_GATE_TRACE_LINKS_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(link, ensure_ascii=True) + "\n")
    link["path"] = EVAL_GATE_TRACE_LINKS_REL_PATH.as_posix()
    return link
