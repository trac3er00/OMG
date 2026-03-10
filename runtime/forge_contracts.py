from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import cast

from lab.policies import validate_job_request
from runtime.domain_packs import DOMAIN_PACKS, get_domain_pack_contract
from runtime.forge_domains import canonical_domain_for, get_all_canonical_domains, is_valid_domain
from runtime.runtime_contracts import read_defense_state, read_session_health

FORGE_STAGE_ORDER: tuple[str, ...] = (
    "data_prepare",
    "synthetic_refine",
    "train_distill",
    "evaluate",
    "regression_test",
)

DEFAULT_STAGE_TIMEOUT_MS: dict[str, int] = {
    "data_prepare": 5_000,
    "synthetic_refine": 5_000,
    "train_distill": 5_000,
    "evaluate": 5_000,
    "regression_test": 5_000,
}


ADAPTER_REGISTRY: dict[str, dict[str, object]] = {
    "axolotl": {
        "kind": "training",
        "module": "axolotl",
        "hook": "lab.axolotl_adapter.run",
        "specialist": "training-architect",
    },
    "pybullet": {
        "kind": "simulator",
        "module": "pybullet",
        "hook": "lab.pybullet_adapter.run",
        "specialist": "simulator-engineer",
        "primary": True,
    },
    "gazebo": {
        "kind": "simulator",
        "module": "gazebo",
        "hook": "lab.gazebo_adapter.run",
        "specialist": "simulator-engineer",
        "primary": False,
    },
    "isaac_gym": {
        "kind": "simulator",
        "module": "isaacgym",
        "hook": "lab.isaac_gym_adapter.run",
        "specialist": "simulator-engineer",
        "primary": False,
    },
}


def load_forge_mvp() -> dict[str, object]:
    return {
        "axolotl_hook": "lab.axolotl_adapter.run",
        "pybullet_hook": "lab.pybullet_adapter.run",
        "labs_only": True,
        "job_schema": {
            "required": ["dataset", "base_model", "target_metric"],
            "dataset_required": ["name", "license", "source"],
            "base_model_required": ["name", "source", "allow_distill"],
            "optional": ["simulated_metric", "evaluation_notes", "simulator_backend", "require_backend"],
        },
        "evaluation_schema": {
            "required": ["status", "stage", "evaluation_report", "published"],
            "report_required": ["created_at", "metric", "target_metric", "passed", "notes"],
            "artifact": "forge-evaluation-evidence",
        },
        "specialist_dispatch": {
            "axolotl": ["dataset", "base_model", "target_metric"],
            "pybullet": ["dataset", "target_metric", "simulated_metric"],
            "forge-cybersecurity": ["dataset", "base_model", "target_metric", "evaluation_notes"],
        },
        "stage_aliases": {
            "security_review": "regression_test",
            "threat_model": "evaluate",
        },
        "specialist_contracts": {
            "forge-cybersecurity": {
                "labs_only": True,
                "allowed_domains": ["cybersecurity"],
                "evidence_profile": "forge-run",
                "proof_backed_dispatch": True,
                "stage_alias": "regression_test",
                "evidence_outputs": {
                    "sarif": ".omg/evidence/security-*.sarif",
                    "sbom": ".omg/evidence/sbom-*.cdx.json",
                    "license": ".omg/evidence/license-*.json",
                    "security_json": ".omg/evidence/security-*.json",
                },
                "reuses_scanner": "runtime.security_check",
            },
        },
        "adapter_registry": dict(ADAPTER_REGISTRY),
        "canonical_domains": get_all_canonical_domains(),
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
            "cybersecurity": {
                "domain": "cybersecurity",
                "specialists": ["forge-cybersecurity"],
                "dataset": {"name": "cybersecurity", "license": "apache-2.0", "source": "internal-curated"},
                "base_model": {"name": "distill-base-v1", "source": "approved-registry", "allow_distill": True},
                "target_metric": 0.8,
            },
        },
    }


def validate_forge_job(job: dict[str, object]) -> tuple[bool, str]:
    domain = job.get("domain")
    if not domain or not str(domain).strip():
        return False, "domain missing: forge run requires an explicit canonical domain (e.g. 'vision', 'robotics')"
    if not is_valid_domain(str(domain)):
        valid = sorted(get_all_canonical_domains())
        return False, f"unknown domain: {domain!r}. Valid domains: {valid}"
    job["domain"] = canonical_domain_for(str(domain))

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


def read_stage_runtime_snapshots(project_dir: str, run_id: str) -> tuple[dict[str, object], dict[str, object]]:
    defense_payload = read_defense_state(project_dir, run_id=run_id, compat=True)
    health_payload = read_session_health(project_dir, run_id=run_id, compat=True)
    defense_snapshot: dict[str, object] = {}
    session_health_snapshot: dict[str, object] = {}
    if isinstance(defense_payload, dict):
        defense_snapshot = cast(dict[str, object], dict(defense_payload))
    if isinstance(health_payload, dict):
        session_health_snapshot = cast(dict[str, object], dict(health_payload))
    return defense_snapshot, session_health_snapshot


def resolve_stage_timeout_ms(job: Mapping[str, object], stage: str) -> int:
    timeout_value: object | None = None
    stage_timeouts = job.get("stage_timeouts_ms")
    if isinstance(stage_timeouts, Mapping):
        timeout_value = stage_timeouts.get(stage)
    if timeout_value is None:
        timeout_value = DEFAULT_STAGE_TIMEOUT_MS.get(stage, 5_000)

    if isinstance(timeout_value, bool):
        return DEFAULT_STAGE_TIMEOUT_MS.get(stage, 5_000)
    if isinstance(timeout_value, int):
        parsed = timeout_value
    elif isinstance(timeout_value, float):
        parsed = int(timeout_value)
    elif isinstance(timeout_value, str):
        try:
            parsed = int(timeout_value)
        except ValueError:
            return DEFAULT_STAGE_TIMEOUT_MS.get(stage, 5_000)
    else:
        return DEFAULT_STAGE_TIMEOUT_MS.get(stage, 5_000)
    return max(0, parsed)


def build_stage_evidence(
    *,
    stage: str,
    run_id: str,
    status: str,
    started_at_ms: float,
    defense_snapshot: Mapping[str, object],
    session_health_snapshot: Mapping[str, object],
    artifacts: list[str],
    adapter_evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    duration_ms = max(0, int((monotonic() - started_at_ms) * 1000))
    result: dict[str, object] = {
        "stage": stage,
        "run_id": run_id,
        "status": status,
        "duration_ms": duration_ms,
        "defense_snapshot": dict(defense_snapshot),
        "session_health_snapshot": dict(session_health_snapshot),
        "artifacts": list(artifacts),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if adapter_evidence is not None:
        result["adapter_evidence"] = list(adapter_evidence)
    return result


def build_forge_evidence(
    project_dir: str,
    run_id: str,
    job: Mapping[str, object],
    result: Mapping[str, object],
    *,
    stage_evidence: list[Mapping[str, object]] | None = None,
) -> str:
    out_path = Path(project_dir) / ".omg" / "evidence" / f"forge-{run_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    domain = str(job.get("domain", "")).strip()
    specialists_raw = job.get("specialists")
    specialist_str = ",".join(str(s) for s in specialists_raw) if isinstance(specialists_raw, list) else ""

    merged_stage_evidence: list[Mapping[str, object]] = []
    if stage_evidence is not None:
        merged_stage_evidence = list(stage_evidence)
    else:
        existing_stage_evidence = result.get("stage_evidence")
        if isinstance(existing_stage_evidence, list):
            merged_stage_evidence = [
                cast(Mapping[str, object], item)
                for item in existing_stage_evidence
                if isinstance(item, Mapping)
            ]

    job_dict = dict(job)
    context_checksum = hashlib.sha256(json.dumps(job_dict, sort_keys=True).encode()).hexdigest()
    domain_pack = get_domain_pack_contract(domain) if domain in DOMAIN_PACKS else {}
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
        "stages": result.get("stages", []),
        "stage_evidence": merged_stage_evidence,
        "causal_chain": {
            "lock_id": "",
            "waiver_artifact_path": str(out_path),
            "delta_summary": {"forge_run": run_id, "domain": domain, "specialist": specialist_str},
            "verification_status": str(result.get("status", "unknown")),
        },
        "context_checksum": context_checksum,
        "profile_version": "forge-run-v1",
        "intent_gate_version": "1.0.0",
        "domain_pack": domain_pack,
    }

    tmp_path = out_path.with_name(f"{out_path.name}.tmp")
    _ = tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    _ = os.rename(tmp_path, out_path)
    return str(out_path)
