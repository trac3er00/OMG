"""OAL full AI pipeline stub: data -> refine -> train/distill -> evaluate -> regression."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .policies import validate_job_request


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pipeline(job: dict[str, Any]) -> dict[str, Any]:
    ok, reason = validate_job_request(job)
    if not ok:
        return {
            "status": "blocked",
            "stage": "policy",
            "reason": reason,
            "published": False,
            "evaluation_report": None,
        }

    target_metric = float(job.get("target_metric", 0.8))
    simulated_metric = float(job.get("simulated_metric", target_metric))

    stages = [
        {"name": "data_prepare", "status": "ok"},
        {"name": "synthetic_refine", "status": "ok"},
        {"name": "train_distill", "status": "ok"},
        {"name": "evaluate", "status": "ok" if simulated_metric >= target_metric else "fail"},
        {"name": "regression_test", "status": "ok" if simulated_metric >= target_metric else "fail"},
    ]

    report = {
        "created_at": _now(),
        "metric": simulated_metric,
        "target_metric": target_metric,
        "passed": simulated_metric >= target_metric,
        "notes": job.get("evaluation_notes", ""),
    }

    if not report["passed"]:
        return {
            "status": "failed_evaluation",
            "stage": "evaluate",
            "stages": stages,
            "published": False,
            "evaluation_report": report,
        }

    return {
        "status": "ready",
        "stage": "complete",
        "stages": stages,
        "published": False,
        "evaluation_report": report,
    }


def publish_artifact(result: dict[str, Any]) -> dict[str, Any]:
    report = result.get("evaluation_report")
    if not isinstance(report, dict) or not report.get("passed"):
        return {
            "status": "blocked",
            "reason": "evaluation report missing or not passed",
            "published": False,
        }

    out = dict(result)
    out["status"] = "published"
    out["published"] = True
    out["published_at"] = _now()
    return out
