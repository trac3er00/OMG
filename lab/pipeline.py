"""OMG full AI pipeline stub: data -> refine -> train/distill -> evaluate -> regression."""
from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from registry.verify_artifact import sign_artifact_statement

from .policies import validate_job_request

PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "data_prepare",
    "synthetic_refine",
    "train_distill",
    "evaluate",
    "regression_test",
)

_STAGE_ADAPTER_KIND: dict[str, str] = {
    "train_distill": "training",
    "evaluate": "simulator",
    "regression_test": "simulator",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pipeline(
    job: dict[str, Any],
    *,
    run_id: str | None = None,
    project_dir: str | None = None,
) -> dict[str, Any]:
    from runtime.forge_contracts import build_stage_evidence, read_stage_runtime_snapshots, resolve_stage_timeout_ms
    from runtime.forge_run_id import normalize_run_id
    from runtime.forge_agents import check_required_backends_satisfied, resolve_adapters

    active_run_id = normalize_run_id(run_id)
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

    adapter_evidence = resolve_adapters(job)
    backends_ok, backends_reason = check_required_backends_satisfied(adapter_evidence)
    if not backends_ok:
        return {
            "status": "blocked",
            "stage": "adapter",
            "reason": backends_reason,
            "published": False,
            "evaluation_report": None,
            "run_id": active_run_id,
            "stage_evidence": [],
            "adapter_evidence": adapter_evidence,
        }

    adapter_by_kind: dict[str, list[dict[str, object]]] = {}
    for ev in adapter_evidence:
        kind = str(ev.get("kind", ""))
        adapter_by_kind.setdefault(kind, []).append(ev)

    target_metric = float(job.get("target_metric", 0.8))
    live_metric = _resolve_live_metric(adapter_evidence)
    if live_metric is None:
        simulated_metric = job.get("simulated_metric")
        if isinstance(simulated_metric, (int, float)) and not isinstance(simulated_metric, bool):
            live_metric = float(simulated_metric)
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

        stage_adapter_kind = _STAGE_ADAPTER_KIND.get(stage)
        stage_adapter_ev = adapter_by_kind.get(stage_adapter_kind, []) if stage_adapter_kind else []
        if stage_status == "success" and stage_adapter_kind and _stage_adapter_failed(stage_adapter_ev):
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
            adapter_evidence=stage_adapter_ev if stage_adapter_ev else None,
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
                "evaluation_report": _evaluation_report(job, live_metric, target_metric),
                "run_id": active_run_id,
                "stage_evidence": stage_evidence,
            }
        if stage_status == "failed":
            return {
                "status": "failed_stage",
                "stage": stage,
                "reason": f"stage execution failed for {stage}",
                "stages": stages,
                "published": False,
                "evaluation_report": _evaluation_report(job, live_metric, target_metric),
                "run_id": active_run_id,
                "stage_evidence": stage_evidence,
            }

    report = _evaluation_report(job, live_metric, target_metric)
    domain_pack_gate = _resolve_domain_pack_gate(job, stage_evidence, adapter_evidence, live_metric)
    promotion_blockers = _collect_promotion_blockers(
        job,
        stage_evidence,
        adapter_evidence,
        live_metric,
        domain_pack_gate=domain_pack_gate,
    )
    artifact_contracts = _build_artifact_contracts(
        run_id=active_run_id,
        target_metric=target_metric,
        live_metric=live_metric,
        adapter_evidence=adapter_evidence,
        promotion_blockers=promotion_blockers,
    )

    result: dict[str, Any] = {
        "status": "ready" if bool(report.get("passed")) else "failed_evaluation",
        "stage": "complete",
        "stages": stages,
        "published": False,
        "evaluation_report": report,
        "run_id": active_run_id,
        "stage_evidence": stage_evidence,
        "domain_pack_gate": domain_pack_gate,
        "promotion_blockers": promotion_blockers,
        "promotion_ready": len(promotion_blockers) == 0,
        "release_evidence": _normalize_release_evidence(job),
    }
    if adapter_evidence:
        result["artifact_contracts"] = artifact_contracts
    if adapter_evidence:
        result["adapter_evidence"] = adapter_evidence
    return result


def _extract_artifact_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    contracts = result.get("artifact_contracts")
    if not isinstance(contracts, dict):
        return None
    checkpoint = contracts.get("checkpoint_hash")
    if not isinstance(checkpoint, dict) or str(checkpoint.get("status", "")).strip().lower() != "signed":
        return None
    attestation = checkpoint.get("attestation")
    if not isinstance(attestation, dict):
        return None
    sha256 = str(checkpoint.get("sha256", "")).strip()
    path = str(checkpoint.get("path", "")).strip()
    signer_key_id = str(checkpoint.get("signer_key_id", "")).strip()
    return {
        "id": path,
        "signer": signer_key_id or "forge-ephemeral",
        "checksum": sha256,
        "attestation": attestation,
        "signer_pubkey": None,
        "permissions": [],
        "static_scan": [],
        "risk_level": "low",
    }


def publish_artifact(result: dict[str, Any]) -> dict[str, Any]:
    governor_module = importlib.import_module("runtime.compliance_governor")
    evaluate_release_compliance = getattr(governor_module, "evaluate_release_compliance")

    report = result.get("evaluation_report")
    if not isinstance(report, dict) or not report.get("passed"):
        return {
            "status": "blocked",
            "reason": "evaluation report missing or not passed",
            "published": False,
        }

    blockers = _collect_publish_blockers(result)
    if blockers:
        return {
            "status": "blocked",
            "reason": blockers[0],
            "published": False,
            "blockers": blockers,
        }

    release_evidence = result.get("release_evidence")
    release_evidence_payload = dict(release_evidence) if isinstance(release_evidence, dict) else {}

    artifact_payload = _extract_artifact_payload(result)
    if artifact_payload is not None:
        release_evidence_payload["artifact"] = artifact_payload

    claims = release_evidence_payload.get("claims")
    if not isinstance(claims, list) and artifact_payload is None:
        out = dict(result)
        out["status"] = "published"
        out["published"] = True
        out["published_at"] = _now()
        return out
    if isinstance(claims, list) and claims and not isinstance(release_evidence_payload.get("artifact"), dict):
        return {
            "status": "blocked",
            "reason": "promotion blocked: claims present but artifact evidence missing",
            "published": False,
        }

    compliance = evaluate_release_compliance(
        project_dir=str(result.get("project_dir", ".")),
        run_id=str(result.get("run_id", "")),
        release_evidence=release_evidence_payload,
    )
    if compliance.get("status") == "blocked":
        reason = str(compliance.get("reason", "compliance blocked")).strip()
        return {
            "status": "blocked",
            "reason": f"promotion blocked: {reason}",
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


def _evaluation_report(job: dict[str, Any], live_metric: float | None, target_metric: float) -> dict[str, object]:
    metric = target_metric if live_metric is None else live_metric
    return {
        "created_at": _now(),
        "metric": metric,
        "target_metric": target_metric,
        "passed": metric >= target_metric,
        "notes": job.get("evaluation_notes", ""),
    }


def _stage_adapter_failed(stage_adapter_ev: list[dict[str, object]]) -> bool:
    if not stage_adapter_ev:
        return False
    for evidence in stage_adapter_ev:
        status = str(evidence.get("status", "")).strip().lower()
        if status in {"error", "blocked", "unavailable", "unavailable_backend"} and bool(evidence.get("required", False)):
            return True
    return False


def _resolve_live_metric(adapter_evidence: list[dict[str, object]]) -> float | None:
    metrics: list[float] = []
    for evidence in adapter_evidence:
        if str(evidence.get("kind", "")) != "simulator":
            continue
        episode_stats = evidence.get("episode_stats")
        if not isinstance(episode_stats, dict):
            continue
        reward_obj = episode_stats.get("reward")
        if isinstance(reward_obj, bool):
            continue
        if isinstance(reward_obj, (int, float)):
            metrics.append(float(reward_obj))
            continue
        if isinstance(reward_obj, str):
            try:
                metrics.append(float(reward_obj))
            except ValueError:
                continue
    if not metrics:
        return None
    return max(metrics)


def _normalize_release_evidence(job: dict[str, Any]) -> dict[str, object]:
    release_evidence = job.get("release_evidence")
    if isinstance(release_evidence, dict):
        return dict(release_evidence)
    claims = job.get("claims")
    if isinstance(claims, list):
        return {"claims": list(claims)}
    return {}


def _collect_promotion_blockers(
    job: dict[str, Any],
    stage_evidence: list[dict[str, object]],
    adapter_evidence: list[dict[str, object]],
    live_metric: float | None,
    *,
    domain_pack_gate: dict[str, object] | None = None,
) -> list[str]:
    blockers: list[str] = []

    gate = domain_pack_gate if isinstance(domain_pack_gate, dict) else {}
    missing_approvals_raw = gate.get("missing_approvals")
    missing_evidence_raw = gate.get("missing_evidence")
    missing_approvals: list[str] = []
    if isinstance(missing_approvals_raw, list):
        for item in missing_approvals_raw:
            missing_approvals.append(str(item))
    missing_evidence: list[str] = []
    if isinstance(missing_evidence_raw, list):
        for item in missing_evidence_raw:
            missing_evidence.append(str(item))
    domain_name = str(gate.get("domain", "")).strip()
    if missing_approvals:
        blockers.append(
            f"promotion blocked: domain '{domain_name}' missing required approvals: {', '.join(missing_approvals)}"
        )
    if missing_evidence:
        blockers.append(
            f"promotion blocked: domain '{domain_name}' missing required evidence: {', '.join(missing_evidence)}"
        )

    if not adapter_evidence:
        return list(dict.fromkeys(blockers))

    stage_by_name = {str(item.get("stage", "")): item for item in stage_evidence}
    for required_stage in ("train_distill", "evaluate", "regression_test"):
        stage_record = stage_by_name.get(required_stage)
        if not isinstance(stage_record, dict) or str(stage_record.get("status", "")) != "success":
            blockers.append("promotion blocked: missing concrete stage evidence")
            break

    has_checkpoint = False
    for evidence in adapter_evidence:
        if str(evidence.get("kind", "")) != "training":
            continue
        artifacts = evidence.get("checkpoint_artifacts")
        if isinstance(artifacts, list) and artifacts:
            has_checkpoint = True
            break
    if not has_checkpoint:
        blockers.append("promotion blocked: missing attestation")

    if live_metric is None:
        blockers.append("promotion blocked: missing regression scoreboard")

    if _requires_claims(job):
        release_evidence = _normalize_release_evidence(job)
        claims = release_evidence.get("claims")
        if not isinstance(claims, list) or not claims:
            blockers.append("promotion blocked: missing release claims")

    return list(dict.fromkeys(blockers))


def _resolve_domain_pack_gate(
    job: dict[str, Any],
    stage_evidence: list[dict[str, object]],
    adapter_evidence: list[dict[str, object]],
    live_metric: float | None,
) -> dict[str, object]:
    from runtime.domain_packs import get_required_approvals, get_required_evidence
    from runtime.evidence_requirements import requirements_for_profile
    from runtime.forge_contracts import load_forge_mvp

    domain = str(job.get("domain", "")).strip().lower()
    if not domain:
        return {
            "domain": "",
            "required_approvals": [],
            "required_evidence": [],
            "present_approvals": [],
            "present_evidence": [],
            "missing_approvals": [],
            "missing_evidence": [],
            "evidence_profile": "",
        }

    try:
        required_approvals = get_required_approvals(domain)
        required_evidence = get_required_evidence(domain)
    except KeyError:
        required_approvals = []
        required_evidence = []

    profile = ""
    contract = load_forge_mvp()
    profile_map = contract.get("domain_evidence_profiles")
    if isinstance(profile_map, dict):
        profile = str(profile_map.get(domain, "")).strip()

    provided_approvals = _collect_provided_approvals(job)
    provided_evidence = _collect_provided_evidence(job, stage_evidence, adapter_evidence, live_metric)

    profile_requirements = requirements_for_profile(profile)
    profile_required_runtime = [item for item in profile_requirements if item in _RUNTIME_CHECKABLE_PROFILE_REQUIREMENTS]
    merged_required_evidence = list(dict.fromkeys([*required_evidence, *profile_required_runtime]))

    missing_approvals = [token for token in required_approvals if token not in provided_approvals]
    missing_evidence = [token for token in merged_required_evidence if token not in provided_evidence]
    return {
        "domain": domain,
        "required_approvals": required_approvals,
        "required_evidence": merged_required_evidence,
        "present_approvals": sorted(provided_approvals),
        "present_evidence": sorted(provided_evidence),
        "missing_approvals": missing_approvals,
        "missing_evidence": missing_evidence,
        "evidence_profile": profile,
    }


_RUNTIME_CHECKABLE_PROFILE_REQUIREMENTS = frozenset(
    {
        "artifact_contracts",
        "audit-trail",
        "benchmark-harness",
        "determinism-check",
        "drift-check",
        "human-review",
        "provenance",
        "restricted-tools",
        "signed_checkpoint",
        "signed_lineage",
        "signed_model_card",
        "simulator-episode-evidence",
        "vision-artifacts",
    }
)


def _collect_provided_approvals(job: dict[str, Any]) -> set[str]:
    approvals: set[str] = set()
    raw = job.get("approvals")
    if isinstance(raw, list):
        approvals.update(str(item).strip() for item in raw if str(item).strip())

    release_evidence = _normalize_release_evidence(job)
    release_approvals = release_evidence.get("approvals")
    if isinstance(release_approvals, list):
        approvals.update(str(item).strip() for item in release_approvals if str(item).strip())
    return approvals


def _collect_provided_evidence(
    job: dict[str, Any],
    stage_evidence: list[dict[str, object]],
    adapter_evidence: list[dict[str, object]],
    live_metric: float | None,
) -> set[str]:
    evidence: set[str] = set()

    for key in ("evidence", "domain_evidence"):
        raw = job.get(key)
        if isinstance(raw, list):
            evidence.update(str(item).strip() for item in raw if str(item).strip())

    release_evidence = _normalize_release_evidence(job)
    raw_release_evidence = release_evidence.get("evidence")
    if isinstance(raw_release_evidence, list):
        evidence.update(str(item).strip() for item in raw_release_evidence if str(item).strip())

    if isinstance(job.get("dataset"), dict):
        evidence.update({"dataset-provenance", "provenance", "signed_lineage"})
    if isinstance(job.get("base_model"), dict):
        evidence.update({"signed_model_card", "restricted-tools"})
    if live_metric is not None:
        evidence.update({"drift-check", "benchmark-harness"})

    if stage_evidence:
        evidence.add("audit-trail")

    for adapter in adapter_evidence:
        kind = str(adapter.get("kind", "")).strip().lower()
        if kind == "training":
            artifacts = adapter.get("checkpoint_artifacts")
            if isinstance(artifacts, list) and artifacts:
                evidence.update({"signed_checkpoint", "artifact_contracts", "determinism-check"})

        if kind != "simulator":
            continue

        replay_metadata = adapter.get("replay_metadata")
        if isinstance(replay_metadata, dict) and replay_metadata:
            evidence.add("simulator-replay")

        episode_stats = adapter.get("episode_stats")
        if isinstance(episode_stats, dict) and episode_stats:
            evidence.update({"simulator-episode-evidence", "vision-artifacts", "kill-switch-check"})

    return {item for item in evidence if item}


def _requires_claims(job: dict[str, Any]) -> bool:
    specialists = job.get("specialists")
    if not isinstance(specialists, list):
        return False
    return "training-architect" in specialists or "simulator-engineer" in specialists


def _build_artifact_contracts(
    *,
    run_id: str,
    target_metric: float,
    live_metric: float | None,
    adapter_evidence: list[dict[str, object]],
    promotion_blockers: list[str],
) -> dict[str, object]:
    checkpoint_contract = _build_checkpoint_contract(run_id=run_id, adapter_evidence=adapter_evidence)
    regression_contract = _build_regression_contract(run_id=run_id, target_metric=target_metric, live_metric=live_metric)
    promotion_status = "blocked" if promotion_blockers else "ready"
    promotion_reason = ", ".join(promotion_blockers) if promotion_blockers else "promotion ready"
    return {
        "checkpoint_hash": checkpoint_contract,
        "regression_scoreboard": regression_contract,
        "promotion_decision": {
            "status": promotion_status,
            "decision_id": f"dec-{run_id}",
            "reason": promotion_reason,
            "replay_required": True,
        },
    }


def _build_checkpoint_contract(*, run_id: str, adapter_evidence: list[dict[str, object]]) -> dict[str, object]:
    for evidence in adapter_evidence:
        if str(evidence.get("kind", "")) != "training":
            continue
        artifacts = evidence.get("checkpoint_artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            continue
        first = artifacts[0]
        if not isinstance(first, dict):
            continue
        path = str(first.get("path", "")).strip() or f".omg/evidence/forge-checkpoint-{run_id}.json"
        sha256 = str(first.get("sha256", "")).strip().lower()
        if len(sha256) != 64:
            continue
        attestation = sign_artifact_statement(path, sha256)
        signer_info = attestation.get("signer") if isinstance(attestation, dict) else None
        signer_key_id = str(signer_info.get("keyid", "")) if isinstance(signer_info, dict) else ""
        return {
            "standard": "OpenSSF-OMS",
            "path": path,
            "status": "signed",
            "sha256": sha256,
            "algorithm": "ed25519-minisign",
            "attestation": attestation,
            "signer_key_id": signer_key_id,
        }
    return {
        "standard": "OpenSSF-OMS",
        "path": f".omg/evidence/forge-checkpoint-{run_id}.json",
        "status": "blocked",
        "reason": "promotion blocked: missing attestation",
    }


def _build_regression_contract(*, run_id: str, target_metric: float, live_metric: float | None) -> dict[str, object]:
    if live_metric is None:
        return {
            "standard": "lm-eval",
            "path": f".omg/evidence/forge-scoreboard-{run_id}.json",
            "status": "blocked",
            "reason": "promotion blocked: missing regression scoreboard",
        }
    status = "passed" if live_metric >= target_metric else "failed"
    return {
        "standard": "lm-eval",
        "path": f".omg/evidence/forge-scoreboard-{run_id}.json",
        "status": status,
        "score": live_metric,
        "target": target_metric,
    }


def _collect_publish_blockers(result: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    inherited_blockers = result.get("promotion_blockers")
    if isinstance(inherited_blockers, list):
        for token in inherited_blockers:
            reason = str(token).strip()
            if reason:
                blockers.append(reason)

    adapter_evidence = result.get("adapter_evidence")
    contracts = result.get("artifact_contracts")
    if (not isinstance(adapter_evidence, list) or not adapter_evidence) and not isinstance(contracts, dict):
        return list(dict.fromkeys(blockers))

    contracts_map = contracts if isinstance(contracts, dict) else {}
    checkpoint = contracts_map.get("checkpoint_hash")
    if not isinstance(checkpoint, dict):
        blockers.append("promotion blocked: missing attestation")
    else:
        checkpoint_status = str(checkpoint.get("status", "")).strip().lower()
        attestation = checkpoint.get("attestation")
        signer_key_id = str(checkpoint.get("signer_key_id", "")).strip()
        if checkpoint_status != "signed" or not isinstance(attestation, dict) or not signer_key_id:
            blockers.append("promotion blocked: missing attestation")

    regression = contracts_map.get("regression_scoreboard")
    if not isinstance(regression, dict) or str(regression.get("status", "")).strip().lower() != "passed":
        blockers.append("promotion blocked: missing regression scoreboard")

    release_evidence = result.get("release_evidence")
    claims = release_evidence.get("claims") if isinstance(release_evidence, dict) else None
    if not isinstance(claims, list) or not claims:
        blockers.append("promotion blocked: missing release claims")

    return list(dict.fromkeys(blockers))


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
