from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from registry.verify_artifact import sign_artifact_statement
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

_OPERATION_SYNONYMS: dict[str, set[str]] = {
    "add": {"add", "create", "insert", "new", "introduce", "build"},
    "edit": {"edit", "update", "modify", "change", "adjust", "revise", "patch"},
    "delete": {"delete", "remove", "drop", "retire", "deprecate", "decommission"},
}

_OPERATION_TEXT_KEYS: tuple[str, ...] = ("goal", "request", "prompt", "task", "summary", "description")


def _normalize_operation_candidate(value: object) -> str:
    candidate = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    if not candidate:
        return ""
    if candidate in _OPERATION_SYNONYMS:
        return candidate
    for intent, synonyms in _OPERATION_SYNONYMS.items():
        if candidate in synonyms:
            return intent
    return ""


def classify_operation_intent(job: dict[str, Any]) -> dict[str, str]:
    for key in ("operation", "intent", "change_type", "action"):
        if key in job:
            normalized = _normalize_operation_candidate(job.get(key))
            if normalized:
                return {"intent": normalized, "source": key}

    for key in _OPERATION_TEXT_KEYS:
        raw_value = str(job.get(key, "") or "")
        text = raw_value.lower()
        if not text:
            continue
        for intent, synonyms in _OPERATION_SYNONYMS.items():
            if any(re.search(rf"\b{re.escape(token)}\b", text) for token in synonyms):
                return {"intent": intent, "source": key}

    return {"intent": "unknown", "source": "none"}


def resolve_operation_plan(job: dict[str, Any]) -> dict[str, Any]:
    contract = load_forge_mvp()
    orchestration = contract.get("operation_orchestration")
    profiles = orchestration if isinstance(orchestration, dict) else {}
    classified = classify_operation_intent(job)
    intent = str(classified.get("intent", "unknown"))
    profile_raw = profiles.get(intent, profiles.get("unknown", {}))
    profile = profile_raw if isinstance(profile_raw, dict) else {}
    checks_raw = profile.get("required_checks")
    required_checks = [str(entry) for entry in checks_raw] if isinstance(checks_raw, list) else []
    return {
        "intent": intent,
        "source": str(classified.get("source", "none")),
        "mode": str(profile.get("mode", "bounded_execution")),
        "priority": str(profile.get("priority", "contract_defaults")),
        "required_checks": required_checks,
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
    operation_plan = resolve_operation_plan(job)

    job_with_specialists = dict(job)
    job_with_specialists["specialists"] = specialists_dispatched
    adapter_evidence = resolve_adapters(job_with_specialists, operation_plan=operation_plan)

    backends_ok, backends_reason = check_required_backends_satisfied(adapter_evidence)
    if not backends_ok:
        return {
            "status": "blocked",
            "specialists_dispatched": specialists_dispatched,
            "evidence_path": "",
            "reason": backends_reason,
            "adapter_evidence": adapter_evidence,
            "operation_plan": operation_plan,
        }

    security_scan: dict[str, Any] | None = None
    if "forge-cybersecurity" in specialists_dispatched:
        security_scan = _execute_cybersecurity_scan(project_dir)

    artifact_contracts, simulator_episode_evidence = _generate_signed_artifact_contracts(
        project_dir=project_dir,
        run_id=active_run_id,
        domain=domain,
        job=job,
        adapter_evidence=adapter_evidence,
    )

    evidence_path = _write_dispatch_evidence(
        project_dir=project_dir,
        run_id=active_run_id,
        snapshot_run_id=run_id,
        status=status,
        domain=domain,
        expected_specialists=expected_specialists,
        requested_specialists=requested_specialists,
        specialists_dispatched=specialists_dispatched,
        operation_plan=operation_plan,
        job=job,
        artifact_contracts=artifact_contracts,
        simulator_episode_evidence=simulator_episode_evidence,
        security_scan=security_scan,
    )
    result_payload: dict[str, Any] = {
        "status": status,
        "specialists_dispatched": specialists_dispatched,
        "run_id": active_run_id,
        "evidence_path": evidence_path,
        "adapter_evidence": adapter_evidence,
        "operation_plan": operation_plan,
        "artifact_contracts": artifact_contracts,
    }
    if simulator_episode_evidence:
        result_payload["simulator_episode_evidence"] = simulator_episode_evidence
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


def _resolve_simulator_adapter(job: dict[str, Any], *, backend: str, required: bool) -> dict[str, object]:
    adapter_hooks: dict[str, str] = {
        "pybullet": "lab.pybullet_adapter",
        "gazebo": "lab.gazebo_adapter",
        "isaac_gym": "lab.isaac_gym_adapter",
    }
    module_name = adapter_hooks.get(backend)
    if not module_name:
        return {
            "adapter": backend,
            "kind": "simulator",
            "status": "error",
            "required": required,
            "reason": f"unknown simulator backend: {backend}",
            "available": False,
        }

    module = importlib.import_module(module_name)
    run_adapter = getattr(module, "run")

    run_id = str(job.get("run_id", "")).strip() or None
    sandbox_root = str(job.get("project_dir", "."))
    raw_timeout = job.get("simulator_timeout_seconds", 30)
    try:
        timeout_seconds = max(1, int(raw_timeout))
    except (TypeError, ValueError):
        timeout_seconds = 30

    evidence = run_adapter(
        job,
        backend_mode="live",
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        sandbox_root=sandbox_root,
    )
    status = str(evidence.get("status", "error"))
    if not required and status == "unavailable_backend":
        status = "skipped_unavailable_backend"
    normalized: dict[str, object] = {
        "adapter": backend,
        "kind": "simulator",
        "status": status,
        "required": required,
        "reason": str(evidence.get("reason", "")),
        "available": bool(evidence.get("available", False)),
    }
    for key in (
        "backend",
        "seed",
        "episode_stats",
        "replay_metadata",
        "availability_reason",
        "fidelity_backend",
        "throughput_role",
        "run_id",
    ):
        if key in evidence:
            normalized[key] = evidence[key]
    normalized["promotion_blocked"] = bool(required and status in {"unavailable_backend", "skipped_unavailable_backend", "error", "blocked"})
    if not required:
        normalized["promotion_blocked"] = False
    return normalized


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


def resolve_adapters(job: dict[str, Any], operation_plan: dict[str, Any] | None = None) -> list[dict[str, object]]:
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
            is_required = require_backend and requested_backend == backend
            results.append(_resolve_simulator_adapter(job, backend=backend, required=is_required))

    if operation_plan is not None:
        for evidence in results:
            evidence["orchestration"] = {
                "operation_plan": {
                    "intent": str(operation_plan.get("intent", "unknown")),
                    "mode": str(operation_plan.get("mode", "bounded_execution")),
                    "priority": str(operation_plan.get("priority", "contract_defaults")),
                }
            }

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


def _generate_signed_artifact_contracts(
    *,
    project_dir: str,
    run_id: str,
    domain: str,
    job: dict[str, Any],
    adapter_evidence: list[dict[str, object]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    evidence_dir = Path(project_dir) / ".omg" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    lineage_payload = {
        "schema": "ForgeDatasetLineage",
        "run_id": run_id,
        "domain": domain,
        "dataset": job.get("dataset", {}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    lineage_path = evidence_dir / f"forge-lineage-{run_id}.json"
    lineage_contract = _write_signed_json_contract(
        project_dir=project_dir,
        path=lineage_path,
        payload=lineage_payload,
        standard="Croissant-1.1",
        extra={"deterministic_metadata": True},
    )

    model_card_path = evidence_dir / f"forge-model-card-{run_id}.md"
    model_card_content = "\n".join(
        [
            f"# Forge Model Card ({run_id})",
            "",
            f"- Domain: {domain}",
            f"- Base model: {str((job.get('base_model') or {}).get('name', 'unknown'))}",
            f"- Dataset: {str((job.get('dataset') or {}).get('name', 'unknown'))}",
            f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
            "- Labs-only: true",
        ]
    )
    model_card_contract = _write_signed_text_contract(
        project_dir=project_dir,
        path=model_card_path,
        content=model_card_content,
        standard="HuggingFace-ModelCard",
        extra={
            "model_id": f"forge-model-{run_id}",
            "base_model": str((job.get("base_model") or {}).get("name", "unknown")),
        },
    )

    checkpoint_sha = _resolve_checkpoint_sha(adapter_evidence, run_id)
    checkpoint_payload = {
        "schema": "ForgeCheckpointDigest",
        "run_id": run_id,
        "domain": domain,
        "sha256": checkpoint_sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint_path = evidence_dir / f"forge-checkpoint-{run_id}.json"
    checkpoint_contract = _write_signed_json_contract(
        project_dir=project_dir,
        path=checkpoint_path,
        payload=checkpoint_payload,
        standard="OpenSSF-OMS",
        extra={"sha256": checkpoint_sha, "algorithm": "ed25519-minisign"},
    )

    simulator_episode_evidence = _write_simulator_episode_evidence(
        project_dir=project_dir,
        run_id=run_id,
        adapter_evidence=adapter_evidence,
    )

    live_metric = _resolve_live_metric(adapter_evidence)
    target_metric = _parse_metric(job.get("target_metric"), fallback=0.0)
    if live_metric is None:
        regression_contract: dict[str, Any] = {
            "standard": "lm-eval",
            "path": f".omg/evidence/forge-scoreboard-{run_id}.json",
            "status": "blocked",
            "reason": "promotion blocked: missing regression scoreboard",
        }
    else:
        regression_contract = {
            "standard": "lm-eval",
            "path": f".omg/evidence/forge-scoreboard-{run_id}.json",
            "status": "passed" if live_metric >= target_metric else "failed",
            "score": live_metric,
            "target": target_metric,
        }

    promotion_status = "ready" if live_metric is not None else "blocked"
    promotion_reason = "promotion ready" if promotion_status == "ready" else "promotion blocked: missing regression scoreboard"

    contracts: dict[str, Any] = {
        "dataset_lineage": lineage_contract,
        "model_card": model_card_contract,
        "checkpoint_hash": checkpoint_contract,
        "regression_scoreboard": regression_contract,
        "promotion_decision": {
            "status": promotion_status,
            "decision_id": f"dec-{run_id}",
            "reason": promotion_reason,
            "replay_required": True,
        },
    }
    if simulator_episode_evidence is not None:
        contracts["simulator_episode"] = dict(simulator_episode_evidence.get("contract", {}))

    return contracts, simulator_episode_evidence


def _write_signed_json_contract(
    *,
    project_dir: str,
    path: Path,
    payload: dict[str, Any],
    standard: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = json.dumps(payload, indent=2, ensure_ascii=True)
    return _write_signed_text_contract(
        project_dir=project_dir,
        path=path,
        content=text,
        standard=standard,
        extra=extra,
    )


def _write_signed_text_contract(
    *,
    project_dir: str,
    path: Path,
    content: str,
    standard: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    _ = temp_path.write_text(content, encoding="utf-8")
    _ = os.replace(temp_path, path)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    attestation = sign_artifact_statement(str(path), digest)
    signer = attestation.get("signer") if isinstance(attestation, dict) else {}
    signer_key_id = str(signer.get("keyid", "")) if isinstance(signer, dict) else ""

    contract: dict[str, Any] = {
        "standard": standard,
        "path": str(path.relative_to(Path(project_dir))).replace("\\", "/"),
        "status": "signed",
        "sha256": digest,
        "algorithm": "ed25519-minisign",
        "attestation": attestation,
        "signer_key_id": signer_key_id,
    }
    if isinstance(extra, dict):
        contract.update(extra)
    return contract


def _resolve_checkpoint_sha(adapter_evidence: list[dict[str, object]], run_id: str) -> str:
    for evidence in adapter_evidence:
        if str(evidence.get("kind", "")) != "training":
            continue
        artifacts = evidence.get("checkpoint_artifacts")
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            digest = str(artifact.get("sha256", "")).strip().lower()
            if len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest):
                return digest
    return hashlib.sha256(f"checkpoint-{run_id}".encode()).hexdigest()


def _resolve_live_metric(adapter_evidence: list[dict[str, object]]) -> float | None:
    rewards: list[float] = []
    for evidence in adapter_evidence:
        if str(evidence.get("kind", "")) != "simulator":
            continue
        stats = evidence.get("episode_stats")
        if not isinstance(stats, dict):
            continue
        reward = stats.get("reward")
        if isinstance(reward, bool):
            continue
        if isinstance(reward, (int, float)):
            rewards.append(float(reward))
            continue
        if isinstance(reward, str):
            try:
                rewards.append(float(reward))
            except ValueError:
                continue
    if not rewards:
        return None
    return max(rewards)


def _parse_metric(value: object, *, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback


def _write_simulator_episode_evidence(
    *,
    project_dir: str,
    run_id: str,
    adapter_evidence: list[dict[str, object]],
) -> dict[str, Any] | None:
    episodes: list[dict[str, Any]] = []
    for evidence in adapter_evidence:
        if str(evidence.get("kind", "")) != "simulator":
            continue
        stats = evidence.get("episode_stats")
        if not isinstance(stats, dict):
            continue
        normalized_stats = {str(key): value for key, value in stats.items()}
        replay_meta_raw = evidence.get("replay_metadata")
        replay_metadata: dict[str, Any] = {}
        if isinstance(replay_meta_raw, dict):
            replay_metadata = {str(key): value for key, value in replay_meta_raw.items()}
        episodes.append(
            {
                "adapter": str(evidence.get("adapter", "simulator")),
                "run_id": str(evidence.get("run_id", run_id)),
                "status": str(evidence.get("status", "unknown")),
                "episode_stats": normalized_stats,
                "replay_metadata": replay_metadata,
            }
        )

    if not episodes:
        return None

    evidence_path = Path(project_dir) / ".omg" / "evidence" / f"forge-simulator-episodes-{run_id}.json"
    payload = {
        "schema": "ForgeSimulatorEpisodes",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "episodes": episodes,
    }
    contract = _write_signed_json_contract(
        project_dir=project_dir,
        path=evidence_path,
        payload=payload,
        standard="SimulatorEpisodeTrace",
        extra={"episode_count": len(episodes)},
    )
    return {
        "path": contract["path"],
        "episode_count": len(episodes),
        "contract": contract,
    }


def collect_forge_evidence_issues(
    project_dir: str,
    run_id: str,
    *,
    domain_pipeline_only: bool = False,
) -> list[dict[str, object]]:
    evidence_dir = Path(project_dir) / ".omg" / "evidence"
    issues: list[dict[str, object]] = []

    candidate_paths = sorted(evidence_dir.glob(f"forge-specialists-{run_id}*.json"))
    if not candidate_paths:
        candidate_paths = sorted(evidence_dir.glob("forge-specialists-*.json"))

    for path in candidate_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        status = str(payload.get("status", "unknown"))
        domain = str(payload.get("domain", "unknown"))
        if status in {"blocked", "error"}:
            issues.append(
                {
                    "severity": "high",
                    "surface": "forge_runs",
                    "title": f"Forge specialist dispatch blocked ({domain})",
                    "description": f"Forge specialist dispatch status is '{status}' for domain '{domain}'.",
                    "fix_guidance": "Repair failing specialist/adapter contracts before release promotion.",
                    "evidence_links": [str(path.relative_to(project_dir)).replace("\\", "/")],
                    "approval_required": True,
                    "approval_reason": "signed approval required to bypass blocked forge workflows",
                }
            )

        contracts = payload.get("artifact_contracts", {})
        if isinstance(contracts, dict):
            for name, contract in contracts.items():
                if not isinstance(contract, dict):
                    continue
                contract_status = str(contract.get("status", ""))
                if contract_status in {"pending", "pending_verification", "insufficient_evidence"}:
                    issues.append(
                        {
                            "severity": "medium",
                            "surface": "domain_pipelines" if domain_pipeline_only else "forge_runs",
                            "title": f"Forge artifact contract incomplete: {name}",
                            "description": (
                                f"Artifact contract '{name}' is '{contract_status}' for forge run domain '{domain}'."
                            ),
                            "fix_guidance": "Generate missing artifact evidence and rerun verification.",
                            "evidence_links": [str(path.relative_to(project_dir)).replace("\\", "/")],
                            "approval_required": False,
                            "approval_reason": "",
                        }
                    )

    if domain_pipeline_only:
        return [issue for issue in issues if issue.get("surface") == "domain_pipelines"]
    return issues


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
    operation_plan: dict[str, Any],
    job: dict[str, Any],
    artifact_contracts: dict[str, Any],
    simulator_episode_evidence: dict[str, Any] | None,
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
        "operation_plan": operation_plan,
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
        "artifact_contracts": artifact_contracts,
    }

    if simulator_episode_evidence is not None:
        payload["simulator_episode_evidence"] = simulator_episode_evidence

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
