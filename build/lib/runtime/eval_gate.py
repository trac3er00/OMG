"""Reproducible evaluation results for release gating."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


EVAL_GATE_LATEST_REL_PATH = Path(".omg") / "evals" / "latest.json"
EVAL_GATE_HISTORY_REL_PATH = Path(".omg") / "evals" / "history.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_trace(
    project_dir: str,
    *,
    trace_id: str,
    suites: list[str],
    metrics: dict[str, float],
    regression_threshold: float = 0.95,
) -> dict[str, Any]:
    scorecard = {name: float(metrics.get(name, 0.0)) for name in suites}
    regressed = any(score < regression_threshold for score in scorecard.values())
    result = {
        "schema": "EvalGateResult",
        "trace_id": trace_id,
        "evaluated_at": _now(),
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
    latest_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    history_path = Path(project_dir) / EVAL_GATE_HISTORY_REL_PATH
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=True) + "\n")

    result["path"] = EVAL_GATE_LATEST_REL_PATH.as_posix()
    return result
