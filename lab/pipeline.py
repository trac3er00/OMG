# pyright: reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false
"""OMG full AI pipeline stub: data -> refine -> train/distill -> evaluate -> regression."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from .policies import validate_job_request

PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "data_prepare",
    "synthetic_refine",
    "train_distill",
    "evaluate",
    "regression_test",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pipeline(
    job: dict[str, Any],
    *,
    run_id: str | None = None,
    project_dir: str | None = None,
) -> dict[str, Any]:
    from runtime.forge_contracts import build_stage_evidence, read_stage_runtime_snapshots, resolve_stage_timeout_ms

    active_run_id = str(run_id or _now())
    ok, reason = validate_job_request(job)
    if not ok:
        return {
            "status": "blocked",
            "stage": "policy",
            "reason": reason,
            "published": False,
            "evaluation_report": None,
            "run_id": active_run_id,
            "stage_evidence": [],
        }

    target_metric = float(job.get("target_metric", 0.8))
    simulated_metric = float(job.get("simulated_metric", target_metric))
    failed_stages = _normalize_stage_set(job.get("stage_failures"))
    explicit_failed_stage = str(job.get("fail_stage", "")).strip().lower()
    if explicit_failed_stage:
        failed_stages.add(explicit_failed_stage)

    stage_durations_ms = _normalize_int_map(job.get("stage_durations_ms"))
    stage_artifacts = _normalize_artifact_map(job.get("stage_artifacts"))

    stages: list[dict[str, str]] = []
    stage_evidence: list[dict[str, object]] = []
    snapshot_root = str(Path(project_dir)) if project_dir else ""

    for stage in PIPELINE_STAGE_ORDER:
        started_at = monotonic()
        stage_status = "success"
        timeout_ms = resolve_stage_timeout_ms(job, stage)
        requested_duration_ms = stage_durations_ms.get(stage, 0)

        if timeout_ms == 0 or requested_duration_ms > timeout_ms:
            stage_status = "timeout"
        elif stage in failed_stages:
            stage_status = "failed"
        elif stage in {"evaluate", "regression_test"} and simulated_metric < target_metric:
            stage_status = "failed"

        defense_snapshot: dict[str, object] = {}
        session_health_snapshot: dict[str, object] = {}
        if snapshot_root:
            defense_snapshot, session_health_snapshot = read_stage_runtime_snapshots(snapshot_root, active_run_id)

        stage_record = build_stage_evidence(
            stage=stage,
            run_id=active_run_id,
            status=stage_status,
            started_at_ms=started_at,
            defense_snapshot=defense_snapshot,
            session_health_snapshot=session_health_snapshot,
            artifacts=stage_artifacts.get(stage, []),
        )
        stage_evidence.append(stage_record)
        stages.append({"name": stage, "status": _to_legacy_stage_status(stage_status)})

        if stage_status == "timeout":
            return {
                "status": "stage_timeout",
                "stage": stage,
                "reason": f"stage timeout envelope exceeded for {stage}",
                "stages": stages,
                "published": False,
                "evaluation_report": _evaluation_report(job, simulated_metric, target_metric),
                "run_id": active_run_id,
                "stage_evidence": stage_evidence,
            }
        if stage_status == "failed":
            if stage in {"evaluate", "regression_test"} and simulated_metric < target_metric:
                return {
                    "status": "failed_evaluation",
                    "stage": "evaluate",
                    "stages": stages,
                    "published": False,
                    "evaluation_report": _evaluation_report(job, simulated_metric, target_metric),
                    "run_id": active_run_id,
                    "stage_evidence": stage_evidence,
                }
            return {
                "status": "failed_stage",
                "stage": stage,
                "reason": f"stage execution failed for {stage}",
                "stages": stages,
                "published": False,
                "evaluation_report": _evaluation_report(job, simulated_metric, target_metric),
                "run_id": active_run_id,
                "stage_evidence": stage_evidence,
            }

    report = _evaluation_report(job, simulated_metric, target_metric)

    return {
        "status": "ready",
        "stage": "complete",
        "stages": stages,
        "published": False,
        "evaluation_report": report,
        "run_id": active_run_id,
        "stage_evidence": stage_evidence,
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


def run_pipeline_with_evidence(project_dir: str, job: dict[str, Any], run_id: str) -> dict[str, Any]:
    from runtime.forge_contracts import build_forge_evidence

    result = run_pipeline(job, run_id=run_id, project_dir=project_dir)
    evidence_path = build_forge_evidence(
        project_dir=project_dir,
        run_id=run_id,
        job=job,
        result=result,
        stage_evidence=result.get("stage_evidence", []),
    )
    out = dict(result)
    out["evidence_path"] = evidence_path
    out["labs_only"] = True
    out["proof_backed"] = True
    return out


def _evaluation_report(job: dict[str, Any], simulated_metric: float, target_metric: float) -> dict[str, object]:
    return {
        "created_at": _now(),
        "metric": simulated_metric,
        "target_metric": target_metric,
        "passed": simulated_metric >= target_metric,
        "notes": job.get("evaluation_notes", ""),
    }


def _normalize_stage_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value:
        stage = str(item).strip().lower()
        if stage in PIPELINE_STAGE_ORDER:
            out.add(stage)
    return out


def _normalize_int_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for raw_key, raw_value in value.items():
        stage = str(raw_key).strip().lower()
        if stage not in PIPELINE_STAGE_ORDER:
            continue
        try:
            out[stage] = max(0, int(raw_value))
        except (TypeError, ValueError):
            continue
    return out


def _normalize_artifact_map(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[str]] = {}
    for raw_key, raw_value in value.items():
        stage = str(raw_key).strip().lower()
        if stage not in PIPELINE_STAGE_ORDER or not isinstance(raw_value, list):
            continue
        out[stage] = [str(item) for item in raw_value]
    return out


def _to_legacy_stage_status(stage_status: str) -> str:
    if stage_status == "success":
        return "ok"
    if stage_status == "timeout":
        return "timeout"
    return "fail"
