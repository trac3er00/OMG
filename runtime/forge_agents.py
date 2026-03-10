from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.domain_packs import DOMAIN_PACKS, get_domain_pack_contract
from runtime.forge_contracts import ADAPTER_REGISTRY, load_forge_mvp, validate_forge_job
from runtime.forge_domains import canonical_domain_for, is_valid_domain
from runtime.forge_run_id import normalize_run_id
from runtime.runtime_contracts import read_defense_state, read_session_health
from runtime.security_check import run_security_check


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
    "vision": ["data-curator", "training-architect", "simulator-engineer"],
    "robotics": ["training-architect", "simulator-engineer"],
    "algorithms": ["training-architect"],
    "health": ["data-curator", "training-architect"],
    "cybersecurity": ["forge-cybersecurity"],
}


def resolve_specialists(domain: str) -> list[str]:
    normalized = str(domain or "").strip().lower()
    if is_valid_domain(normalized):
        normalized = canonical_domain_for(normalized)
    return list(_DOMAIN_SPECIALISTS.get(normalized, []))


def get_specialist_registry() -> dict[str, dict[str, object]]:
    return {name: dict(metadata) for name, metadata in _SPECIALIST_REGISTRY.items()}



def _execute_cybersecurity_scan(project_dir: str) -> dict[str, Any]:
    """Run canonical security_check scan for forge-cybersecurity specialist.

    Reuses runtime/security_check.py engine. Degrades gracefully
    when Semgrep or other external tools are unavailable.
    """
    try:
        return run_security_check(
            project_dir=project_dir,
            scope=".",
            include_live_enrichment=False,
        )
    except Exception:
        return {
            "schema": "SecurityCheckResult",
            "status": "error",
            "scope": ".",
            "findings": [],
            "security_scans": [],
            "unresolved_risks": [],
            "evidence": {},
            "summary": {"scan_status": "failed", "finding_count": 0},
        }


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
    active_run_id = normalize_run_id(run_id)

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

    security_scan: dict[str, Any] | None = None
    if "forge-cybersecurity" in specialists_dispatched:
        security_scan = _execute_cybersecurity_scan(project_dir)

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
        security_scan=security_scan,
    )
    result_payload: dict[str, Any] = {
        "status": status,
        "specialists_dispatched": specialists_dispatched,
        "run_id": active_run_id,
        "evidence_path": evidence_path,
        "adapter_evidence": adapter_evidence,
    }
    if security_scan is not None:
        result_payload["security_scan"] = security_scan
    return result_payload


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


def _resolve_axolotl_mode(job: dict[str, Any]) -> str:
    explicit_mode = str(job.get("axolotl_mode", "")).strip().lower()
    if explicit_mode:
        return explicit_mode
    reward_heads = job.get("reward_heads")
    if isinstance(reward_heads, bool):
        return "live_sft"
    if isinstance(reward_heads, (int, float)):
        count = int(reward_heads)
    elif isinstance(reward_heads, list):
        count = len(reward_heads)
    elif isinstance(reward_heads, dict):
        count = len(reward_heads)
    elif isinstance(reward_heads, str) and reward_heads.strip().isdigit():
        count = int(reward_heads.strip())
    else:
        count = 0
    if count > 1:
        return "live_gdpo"
    if count == 1:
        return "live_grpo"
    return "live_sft"


def _resolve_axolotl_adapter(job: dict[str, Any], *, required: bool) -> dict[str, object]:
    from lab.axolotl_adapter import run as run_axolotl_adapter

    mode = _resolve_axolotl_mode(job)
    run_id = str(job.get("run_id", "")).strip() or None
    sandbox_root = str(job.get("project_dir", "."))
    raw_timeout = job.get("axolotl_timeout_seconds", 30)
    try:
        timeout_seconds = max(1, int(raw_timeout))
    except (TypeError, ValueError):
        timeout_seconds = 30

    evidence = run_axolotl_adapter(
        job,
        backend_mode=mode,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        sandbox_root=sandbox_root,
    )

    status = str(evidence.get("status", "error"))
    reason = str(evidence.get("reason", ""))
    available = bool(evidence.get("available", False))

    if not required and status == "unavailable_backend":
        status = "skipped_unavailable_backend"

    normalized: dict[str, object] = {
        "adapter": "axolotl",
        "kind": "training",
        "status": status,
        "required": required,
        "reason": reason,
        "available": available,
        "mode": str(evidence.get("mode", mode)),
    }
    for key in (
        "run_id",
        "evidence_path",
        "checkpoint_path",
        "checkpoint_paths",
        "checkpoint_artifacts",
        "search_scores",
        "search_best_trial",
        "resume_metadata",
        "sidecar_required",
        "sidecar_evidence_path",
    ):
        if key in evidence:
            normalized[key] = evidence[key]
    if "promotion_blocked" in evidence:
        normalized["promotion_blocked"] = evidence["promotion_blocked"] if required else False
    return normalized


def resolve_adapters(job: dict[str, Any]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    dispatched_specialists = job.get("specialists", [])
    if not isinstance(dispatched_specialists, list):
        dispatched_specialists = []

    requested_backend = str(job.get("simulator_backend", "")).strip().lower()
    require_backend = bool(job.get("require_backend", False))

    if "training-architect" in dispatched_specialists:
        axolotl_required = require_backend and requested_backend == "axolotl"
        results.append(_resolve_axolotl_adapter(job, required=axolotl_required))

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
    unavailable_statuses = {
        "skipped_unavailable_backend",
        "unavailable",
        "unavailable_backend",
        "error",
        "blocked",
    }
    for ev in adapter_evidence:
        status = str(ev.get("status", ""))
        if ev.get("required") is True and status in unavailable_statuses:
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
    security_scan: dict[str, Any] | None = None,
) -> str:
    evidence_dir = Path(project_dir) / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"forge-specialists-{run_id}.json"
    contract = load_forge_mvp()
    context_checksum = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()
    domain_pack = get_domain_pack_contract(domain) if domain in DOMAIN_PACKS else {}
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
        "context_checksum": context_checksum,
        "profile_version": "forge-run-v1",
        "intent_gate_version": "1.0.0",
        "domain_pack": domain_pack,
        "artifact_contracts": {
            "dataset_lineage": {
                "standard": "Croissant-1.1",
                "path": f".omg/evidence/forge-lineage-{run_id}.json",
                "status": "placeholder",
                "reason": "dataset lineage artifact not yet generated",
            },
            "model_card": {
                "standard": "HuggingFace-ModelCard",
                "path": f".omg/evidence/forge-model-card-{run_id}.md",
                "status": "placeholder",
                "reason": "model card artifact not yet generated",
            },
            "checkpoint_hash": {
                "standard": "OpenSSF-OMS",
                "path": f".omg/evidence/forge-checkpoint-{run_id}.json",
                "status": "placeholder",
                "reason": "checkpoint hash artifact not yet generated",
            },
            "regression_scoreboard": {
                "standard": "lm-eval",
                "path": f".omg/evidence/forge-scoreboard-{run_id}.json",
                "status": "placeholder",
                "reason": "regression scoreboard artifact not yet generated",
            },
            "promotion_decision": {
                "status": "pending",
                "reason": "promotion requires passing regression scoreboard and human review for health domain",
                "replay_required": True,
            },
        },
    }

    if domain == "cybersecurity":
        evidence_dir = evidence_path.parent
        security_links: list[str] = []
        for pattern in ("security-*.json", "security-*.sarif"):
            security_links.extend(
                f".omg/evidence/{p.name}" for p in sorted(evidence_dir.glob(pattern))
            )
        payload["security_evidence_links"] = security_links if security_links else [
            ".omg/evidence/security-*.json",
            ".omg/evidence/security-*.sarif",
        ]

    if security_scan is not None:
        payload["security_scan"] = security_scan

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
