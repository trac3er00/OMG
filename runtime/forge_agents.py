from __future__ import annotations

import importlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.forge_contracts import ADAPTER_REGISTRY, load_forge_mvp, validate_forge_job
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
    "forge-cybersecurity": {
        "description": "Runs labs-bounded cybersecurity hardening and threat-evidence checks.",
        "capabilities": ["threat-modeling", "security-regression", "proof-linked-security-evidence"],
    },
}

_DOMAIN_SPECIALISTS: dict[str, list[str]] = {
    "vision-agent": ["data-curator", "training-architect", "simulator-engineer"],
    "vision": ["data-curator", "training-architect", "simulator-engineer"],
    "robotics": ["training-architect", "simulator-engineer"],
    "algorithms": ["training-architect"],
    "health": ["data-curator", "training-architect"],
    "cybersecurity": ["forge-cybersecurity"],
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

    job_with_specialists = dict(job)
    job_with_specialists["specialists"] = specialists_dispatched
    adapter_evidence = resolve_adapters(job_with_specialists)

    backends_ok, backends_reason = check_required_backends_satisfied(adapter_evidence)
    if not backends_ok:
        return {
            "status": "blocked",
            "specialists_dispatched": specialists_dispatched,
            "evidence_path": "",
            "reason": backends_reason,
            "adapter_evidence": adapter_evidence,
        }

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
        "adapter_evidence": adapter_evidence,
    }


def _resolve_specialist_contracts(contract: dict[str, object], specialists: list[str]) -> dict[str, dict[str, object]]:
    raw_contracts = contract.get("specialist_contracts")
    if not isinstance(raw_contracts, dict):
        return {}

    selected: dict[str, dict[str, object]] = {}
    for name in specialists:
        entry = raw_contracts.get(name)
        if isinstance(entry, dict):
            selected[name] = dict(entry)
    return selected


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


def _check_backend_available(backend_name: str) -> bool:
    entry = ADAPTER_REGISTRY.get(backend_name)
    if entry is None:
        return False
    module_name = str(entry.get("module", ""))
    if not module_name:
        return False
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _check_axolotl_available() -> bool:
    return _check_backend_available("axolotl")


def _check_simulator_available(name: str) -> bool:
    return _check_backend_available(name)


def resolve_adapters(job: dict[str, Any]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    dispatched_specialists = job.get("specialists", [])
    if not isinstance(dispatched_specialists, list):
        dispatched_specialists = []

    requested_backend = str(job.get("simulator_backend", "")).strip().lower()
    require_backend = bool(job.get("require_backend", False))

    if "training-architect" in dispatched_specialists:
        available = _check_axolotl_available()
        results.append({
            "adapter": "axolotl",
            "kind": "training",
            "status": "invoked" if available else "skipped_unavailable_backend",
            "required": require_backend and requested_backend == "axolotl",
            "reason": "" if available else "axolotl not installed",
            "available": available,
        })

    if "simulator-engineer" in dispatched_specialists:
        simulator_backends = _resolve_simulator_backends(requested_backend)
        for backend in simulator_backends:
            available = _check_simulator_available(backend)
            is_required = require_backend and requested_backend == backend
            results.append({
                "adapter": backend,
                "kind": "simulator",
                "status": "invoked" if available else "skipped_unavailable_backend",
                "required": is_required,
                "reason": "" if available else f"{backend} not installed",
                "available": available,
            })

    return results


def _resolve_simulator_backends(requested: str) -> list[str]:
    if requested and requested in ADAPTER_REGISTRY:
        entry = ADAPTER_REGISTRY[requested]
        if str(entry.get("kind", "")) == "simulator":
            return [requested]
    return ["pybullet"]


def check_required_backends_satisfied(adapter_evidence: list[dict[str, object]]) -> tuple[bool, str]:
    for ev in adapter_evidence:
        if ev.get("required") is True and ev.get("status") == "skipped_unavailable_backend":
            adapter_name = str(ev.get("adapter", "unknown"))
            return False, f"required backend unavailable: {adapter_name}"
    return True, "ok"


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
        "specialist_contracts": _resolve_specialist_contracts(contract, specialists_dispatched),
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
