from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.forge_contracts import load_forge_mvp, validate_forge_job
from runtime.runtime_contracts import read_defense_state, read_session_health


_SPECIALIST_REGISTRY: dict[str, dict[str, object]] = {
    "data-curator": {
        "description": "Curates policy-compliant datasets and provenance artifacts.",
        "capabilities": ["dataset-lineage", "license-screening", "curation-audit"],
    },
    "training-architect": {
        "description": "Designs bounded distillation/training plans through approved hooks.",
        "capabilities": ["distillation-plan", "axolotl-hook-contract", "eval-readiness"],
    },
    "simulator-engineer": {
        "description": "Builds simulator-backed evaluations through the PyBullet hook contract.",
        "capabilities": ["simulator-scenarios", "pybullet-hook-contract", "regression-replay"],
    },
}

_DOMAIN_SPECIALISTS: dict[str, list[str]] = {
    "vision-agent": ["data-curator", "training-architect", "simulator-engineer"],
    "vision": ["data-curator", "training-architect", "simulator-engineer"],
    "robotics": ["training-architect", "simulator-engineer"],
    "algorithms": ["training-architect"],
    "health": ["data-curator", "training-architect"],
}


def resolve_specialists(domain: str) -> list[str]:
    normalized = str(domain or "").strip().lower()
    return list(_DOMAIN_SPECIALISTS.get(normalized, []))


def get_specialist_registry() -> dict[str, dict[str, object]]:
    return {name: dict(metadata) for name, metadata in _SPECIALIST_REGISTRY.items()}


def dispatch_specialists(job: dict[str, Any], project_dir: str, run_id: str | None = None) -> dict[str, Any]:
    ok, reason = validate_forge_job(job)
    if not ok:
        return {
            "status": "blocked",
            "specialists_dispatched": [],
            "evidence_path": "",
            "reason": reason,
        }

    domain = str(job.get("domain", "")).strip().lower()
    requested_specialists = _normalize_specialist_list(job.get("specialists"))
    expected_specialists = resolve_specialists(domain)

    if requested_specialists and not expected_specialists:
        return {
            "status": "blocked",
            "specialists_dispatched": [],
            "evidence_path": "",
            "reason": "invalid_specialist_domain_combination",
        }

    if requested_specialists:
        unknown = [name for name in requested_specialists if name not in _SPECIALIST_REGISTRY]
        if unknown:
            return {
                "status": "blocked",
                "specialists_dispatched": [],
                "evidence_path": "",
                "reason": f"unknown specialists requested: {', '.join(unknown)}",
            }
        invalid_for_domain = [name for name in requested_specialists if name not in expected_specialists]
        if invalid_for_domain:
            return {
                "status": "blocked",
                "specialists_dispatched": [],
                "evidence_path": "",
                "reason": "invalid_specialist_domain_combination",
            }
        missing_required = [name for name in expected_specialists if name not in requested_specialists]
        if missing_required:
            return {
                "status": "blocked",
                "specialists_dispatched": [],
                "evidence_path": "",
                "reason": "invalid_specialist_domain_combination",
            }

    specialists_dispatched = requested_specialists if requested_specialists else expected_specialists
    status = "ok" if specialists_dispatched else "noop"
    active_run_id = run_id or _now_run_id()
    evidence_path = _write_dispatch_evidence(
        project_dir=project_dir,
        run_id=active_run_id,
        snapshot_run_id=run_id,
        status=status,
        domain=domain,
        expected_specialists=expected_specialists,
        requested_specialists=requested_specialists,
        specialists_dispatched=specialists_dispatched,
        job=job,
    )
    return {
        "status": status,
        "specialists_dispatched": specialists_dispatched,
        "run_id": active_run_id,
        "evidence_path": evidence_path,
    }


def _normalize_specialist_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for entry in value:
        candidate = str(entry).strip().lower()
        if candidate and candidate not in items:
            items.append(candidate)
    return items


def _now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _write_dispatch_evidence(
    *,
    project_dir: str,
    run_id: str,
    snapshot_run_id: str | None,
    status: str,
    domain: str,
    expected_specialists: list[str],
    requested_specialists: list[str],
    specialists_dispatched: list[str],
    job: dict[str, Any],
) -> str:
    evidence_dir = Path(project_dir) / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"forge-specialists-{run_id}.json"
    contract = load_forge_mvp()
    payload: dict[str, Any] = {
        "schema": "ForgeSpecialistDispatchEvidence",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "labs_only": True,
        "proof_backed": True,
        "specialist": ",".join(specialists_dispatched),
        "domain": domain,
        "requested_specialists": requested_specialists,
        "expected_specialists": expected_specialists,
        "specialists_dispatched": specialists_dispatched,
        "contract": {
            "labs_only": bool(contract.get("labs_only", True)),
            "axolotl_hook": contract.get("axolotl_hook", ""),
            "pybullet_hook": contract.get("pybullet_hook", ""),
        },
        "causal_chain": {
            "lock_id": "",
            "waiver_artifact_path": f".omg/evidence/forge-specialists-{run_id}.json",
            "delta_summary": {"forge_dispatch": domain, "specialists": specialists_dispatched},
            "verification_status": status,
        },
        "job": job,
    }

    defense_state = read_defense_state(project_dir, run_id=snapshot_run_id, compat=True)
    session_health = read_session_health(project_dir, run_id=snapshot_run_id, compat=True)
    if isinstance(defense_state, dict):
        payload["defense_state"] = defense_state
    if isinstance(session_health, dict):
        payload["session_health"] = session_health

    tmp_path = evidence_path.with_name(f"{evidence_path.name}.tmp")
    _ = tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    _ = os.replace(tmp_path, evidence_path)
    return str(evidence_path)
