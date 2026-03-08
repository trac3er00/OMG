from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from lab.policies import validate_job_request


def load_forge_mvp() -> dict[str, object]:
    return {
        "axolotl_hook": "lab.axolotl_adapter.run",
        "pybullet_hook": "lab.pybullet_adapter.run",
        "labs_only": True,
        "job_schema": {
            "required": ["dataset", "base_model", "target_metric"],
            "dataset_required": ["name", "license", "source"],
            "base_model_required": ["name", "source", "allow_distill"],
            "optional": ["simulated_metric", "evaluation_notes"],
        },
        "evaluation_schema": {
            "required": ["status", "stage", "evaluation_report", "published"],
            "report_required": ["created_at", "metric", "target_metric", "passed", "notes"],
            "artifact": "forge-evaluation-evidence",
        },
        "specialist_dispatch": {
            "axolotl": ["dataset", "base_model", "target_metric"],
            "pybullet": ["dataset", "target_metric", "simulated_metric"],
        },
        "evidence_output_path": ".omg/evidence/forge-<run_id>.json",
    }


def validate_forge_job(job: dict[str, object]) -> tuple[bool, str]:
    ok, reason = validate_job_request(job)
    if not ok:
        return False, reason

    dataset = job.get("dataset")
    base_model = job.get("base_model")

    if not isinstance(dataset, dict):
        return False, "dataset block missing"
    if not isinstance(base_model, dict):
        return False, "base_model block missing"

    dataset_block = cast(dict[str, object], dataset)
    base_model_block = cast(dict[str, object], base_model)

    if not str(dataset_block.get("name", "")).strip():
        return False, "dataset.name missing"
    if not str(base_model_block.get("name", "")).strip():
        return False, "base_model.name missing"

    target_metric = job.get("target_metric")
    if target_metric is None:
        return False, "target_metric missing or invalid"
    try:
        _ = float(str(target_metric))
    except (TypeError, ValueError):
        return False, "target_metric missing or invalid"

    return True, "ok"


def build_forge_evidence(project_dir: str, run_id: str, job: Mapping[str, object], result: Mapping[str, object]) -> str:
    out_path = Path(project_dir) / ".omg" / "evidence" / f"forge-{run_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "ForgeMVPEvidence",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract": load_forge_mvp(),
        "job": job,
        "result": result,
        "status": result.get("status", "unknown"),
        "evaluation_report": result.get("evaluation_report"),
    }

    tmp_path = out_path.with_name(f"{out_path.name}.tmp")
    _ = tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    _ = os.rename(tmp_path, out_path)
    return str(out_path)
