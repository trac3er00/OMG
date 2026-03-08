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
        "starter_templates": {
            "vision-agent": {
                "domain": "vision-agent",
                "specialists": ["data-curator", "training-architect", "simulator-engineer"],
                "dataset": {"name": "vision-agent", "license": "apache-2.0", "source": "internal-curated"},
                "base_model": {"name": "distill-base-v1", "source": "approved-registry", "allow_distill": True},
                "target_metric": 0.8,
            },
            "robotics": {
                "domain": "robotics",
                "specialists": ["training-architect", "simulator-engineer"],
                "dataset": {"name": "robotics", "license": "apache-2.0", "source": "internal-curated"},
                "base_model": {"name": "distill-base-v1", "source": "approved-registry", "allow_distill": True},
                "target_metric": 0.8,
            },
            "algorithms": {
                "domain": "algorithms",
                "specialists": ["training-architect"],
                "dataset": {"name": "algorithms", "license": "apache-2.0", "source": "internal-curated"},
                "base_model": {"name": "distill-base-v1", "source": "approved-registry", "allow_distill": True},
                "target_metric": 0.8,
            },
            "health": {
                "domain": "health",
                "specialists": ["data-curator", "training-architect"],
                "dataset": {"name": "health", "license": "apache-2.0", "source": "internal-curated"},
                "base_model": {"name": "distill-base-v1", "source": "approved-registry", "allow_distill": True},
                "target_metric": 0.8,
            },
        },
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

    domain = str(job.get("domain", "")).strip()
    specialists_raw = job.get("specialists")
    specialist_str = ",".join(str(s) for s in specialists_raw) if isinstance(specialists_raw, list) else ""

    payload = {
        "schema": "ForgeMVPEvidence",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "labs_only": True,
        "proof_backed": True,
        "specialist": specialist_str,
        "domain": domain,
        "contract": load_forge_mvp(),
        "job": job,
        "result": result,
        "status": result.get("status", "unknown"),
        "evaluation_report": result.get("evaluation_report"),
        "causal_chain": {
            "lock_id": "",
            "waiver_artifact_path": str(out_path),
            "delta_summary": {"forge_run": run_id, "domain": domain, "specialist": specialist_str},
            "verification_status": str(result.get("status", "unknown")),
        },
    }

    tmp_path = out_path.with_name(f"{out_path.name}.tmp")
    _ = tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    _ = os.rename(tmp_path, out_path)
    return str(out_path)
