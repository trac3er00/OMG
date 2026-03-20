from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, cast

from runtime import proof_gate


def propose_skill(name: str, source: str, description: str = "", metadata: dict[str, object] | None = None) -> dict[str, object]:
    normalized_name = str(name).strip()
    normalized_source = str(source).strip()
    if not normalized_name:
        raise ValueError("skill_name_required")
    if not normalized_source:
        raise ValueError("skill_source_required")

    proposal_id = f"proposal-{uuid.uuid4().hex}"
    artifact_path = _proposal_path(proposal_id)
    evaluation_path = _evaluation_path(proposal_id)

    payload = {
        "schema": "SkillProposal",
        "schema_version": 1,
        "proposal_id": proposal_id,
        "status": "proposed",
        "name": normalized_name,
        "source": normalized_source,
        "description": str(description),
        "metadata": dict(metadata or {}),
        "promoted": False,
        "created_at": _timestamp(),
    }
    _atomic_write_json(artifact_path, payload)

    return {
        "status": "proposed",
        "proposal_id": proposal_id,
        "name": normalized_name,
        "source": normalized_source,
        "artifact_path": _relative_to_project(artifact_path),
        "evaluation_path": _relative_to_project(evaluation_path),
        "promoted": False,
    }


def evaluate_proposal(
    proposal_id: str,
    test_results: dict[str, object],
    project_dir: str | None = None,
) -> dict[str, object]:
    normalized_id = str(proposal_id).strip()
    proposal_path = _proposal_path(normalized_id)
    proposal_payload = _read_json(proposal_path)
    if proposal_payload is None:
        proof_gate_result = {
            "schema": "ProofGateResult",
            "verdict": "fail",
            "blockers": ["skill_proposal_missing"],
            "evidence_summary": {"proposal_id": normalized_id},
        }
        return {
            "status": "failed",
            "proposal_id": normalized_id,
            "proof_gate_result": proof_gate_result,
            "promotable": False,
        }

    gate_input = _build_proof_gate_input(normalized_id, test_results)
    proof_gate_result = cast(dict[str, object], proof_gate.evaluate_proof_gate(gate_input))
    base_verdict = str(proof_gate_result.get("verdict", "fail"))
    promotable = base_verdict == "pass"

    # NF6b: Check evidence_runs if present in proposal metadata
    evidence_runs_verdict = None
    metadata = proposal_payload.get("metadata", {})
    if isinstance(metadata, dict):
        evidence_runs = metadata.get("evidence_runs")
        if isinstance(evidence_runs, list) and evidence_runs:
            effective_project_dir = project_dir or str(_project_dir())
            evidence_summary = get_proposal_evidence_summary(normalized_id, effective_project_dir)
            evidence_runs_verdict = evidence_summary.get("verdict")

            # If any evidence run failed, reject the proposal
            if evidence_summary.get("failing_runs", 0) > 0:
                promotable = False
                blockers = list(proof_gate_result.get("blockers", []))  # type: ignore[arg-type]
                blockers.append("evidence_run_failed")
                proof_gate_result = dict(proof_gate_result)
                proof_gate_result["blockers"] = blockers
                if base_verdict == "pass":
                    proof_gate_result["verdict"] = "fail"

            # If all evidence runs passed, increase confidence
            elif evidence_runs_verdict == "promote" and promotable:
                proof_gate_result = dict(proof_gate_result)
                evidence_info = proof_gate_result.get("evidence_summary", {})
                if isinstance(evidence_info, dict):
                    evidence_info = dict(evidence_info)
                    evidence_info["evidence_runs_verified"] = True
                    evidence_info["evidence_runs_count"] = evidence_summary.get("passing_runs", 0)
                    proof_gate_result["evidence_summary"] = evidence_info

    status = "evaluated" if promotable else "failed"

    evaluation_payload = {
        "schema": "SkillProposalEvaluation",
        "schema_version": 1,
        "proposal_id": normalized_id,
        "status": status,
        "promotable": promotable,
        "proof_gate_result": proof_gate_result,
        "test_results": dict(test_results),
        "proposal_path": _relative_to_project(proposal_path),
        "evaluated_at": _timestamp(),
    }
    _atomic_write_json(_evaluation_path(normalized_id), evaluation_payload)

    return {
        "status": status,
        "proposal_id": normalized_id,
        "proof_gate_result": proof_gate_result,
        "promotable": promotable,
    }


def promote_if_proven(proposal_id: str) -> dict[str, object]:
    normalized_id = str(proposal_id).strip()
    proposal_path = _proposal_path(normalized_id)
    if not proposal_path.exists():
        return {
            "status": "missing",
            "proposal_id": normalized_id,
            "reason": "proposal_not_found",
        }

    evaluation_payload = _read_json(_evaluation_path(normalized_id))
    if evaluation_payload is None:
        return {
            "status": "blocked",
            "proposal_id": normalized_id,
            "reason": "evaluation_missing",
        }

    if not bool(evaluation_payload.get("promotable")):
        return {
            "status": "blocked",
            "proposal_id": normalized_id,
            "reason": "proof_gate_failed",
        }

    promotion_payload = {
        "schema": "SkillProposalPromotion",
        "schema_version": 1,
        "proposal_id": normalized_id,
        "status": "promoted",
        "reason": "proof_gate_passed",
        "enabled": False,
        "promoted_at": _timestamp(),
    }
    _atomic_write_json(_promotion_path(normalized_id), promotion_payload)

    return {
        "status": "promoted",
        "proposal_id": normalized_id,
        "reason": "proof_gate_passed",
    }


def _build_proof_gate_input(proposal_id: str, test_results: dict[str, object]) -> dict[str, object]:
    raw_gate_input = test_results.get("proof_gate_input")
    if isinstance(raw_gate_input, dict):
        payload = cast(dict[str, object], dict(raw_gate_input))
        _ = payload.setdefault("evidence_pack", {})
        return payload

    raw_proof_chain = test_results.get("proof_chain")
    proof_chain: dict[str, object]
    if isinstance(raw_proof_chain, dict):
        proof_chain = cast(dict[str, object], dict(raw_proof_chain))
    else:
        proof_chain = {"status": "error", "blockers": ["proof_chain_missing"]}

    raw_eval_output = test_results.get("eval_output")
    eval_output = cast(dict[str, object], dict(raw_eval_output)) if isinstance(raw_eval_output, dict) else {}

    raw_security_evidence = test_results.get("security_evidence")
    security_evidence = cast(dict[str, object], dict(raw_security_evidence)) if isinstance(raw_security_evidence, dict) else {}

    raw_browser_evidence = test_results.get("browser_evidence")
    browser_evidence = cast(dict[str, object], dict(raw_browser_evidence)) if isinstance(raw_browser_evidence, dict) else {}

    raw_claims = test_results.get("claims")
    claims = list(raw_claims) if isinstance(raw_claims, list) else []

    raw_evidence_pack = test_results.get("evidence_pack")
    evidence_pack: dict[str, object] = cast(dict[str, object], dict(raw_evidence_pack)) if isinstance(raw_evidence_pack, dict) else {}
    evidence_pack["proposal_id"] = proposal_id
    return {
        "claims": claims,
        "proof_chain": proof_chain,
        "eval_output": eval_output,
        "security_evidence": security_evidence,
        "browser_evidence": browser_evidence,
        "evidence_pack": evidence_pack,
    }


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _proposal_dir() -> Path:
    return _project_dir() / ".omg" / "state" / "skill-proposals"


def _proposal_path(proposal_id: str) -> Path:
    return _proposal_dir() / f"{proposal_id}.json"


def _evaluation_path(proposal_id: str) -> Path:
    return _proposal_dir() / f"{proposal_id}-eval.json"


def _promotion_path(proposal_id: str) -> Path:
    return _proposal_dir() / f"{proposal_id}-promoted.json"


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    serialized = json.dumps(dict(payload), indent=2, ensure_ascii=True) + "\n"
    _ = temp_path.write_text(serialized, encoding="utf-8")
    os.replace(temp_path, path)


def _relative_to_project(path: Path) -> str:
    return str(path.relative_to(_project_dir()))


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# -----------------------------------------------------------------------------
# NF6a: Automatic workflow detection
# -----------------------------------------------------------------------------


def record_workflow_step(
    project_dir: str,
    tool_name: str,
    args: dict[str, object],
    success: bool,
    run_id: str,
) -> None:
    """Append a workflow step entry to workflow-log.jsonl."""
    normalized_tool = str(tool_name).strip()
    normalized_run_id = str(run_id).strip()
    if not normalized_tool or not normalized_run_id:
        return

    args_hash = _hash_args(args)
    entry = {
        "tool": normalized_tool,
        "args_hash": args_hash,
        "success": success,
        "run_id": normalized_run_id,
        "ts": _timestamp(),
    }

    log_path = _workflow_log_path(project_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def detect_reusable_patterns(
    project_dir: str,
    min_occurrences: int = 3,
) -> list[dict[str, object]]:
    """Find tool sequences that appear min_occurrences+ times with success=True."""
    log_path = _workflow_log_path(project_dir)
    if not log_path.exists():
        return []

    # Group entries by run_id
    runs: dict[str, list[dict[str, object]]] = defaultdict(list)
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            run_id = str(entry.get("run_id", "")).strip()
            if run_id:
                runs[run_id].append(entry)
    except OSError:
        return []

    # Extract successful sequences per run
    sequence_occurrences: dict[str, list[tuple[list[str], str]]] = defaultdict(list)
    for run_id, entries in runs.items():
        # Only include runs where all steps succeeded
        if not entries or not all(bool(e.get("success")) for e in entries):
            continue
        sequence = [str(e.get("tool", "")) for e in entries]
        if not sequence or not all(sequence):
            continue
        seq_hash = _hash_sequence(sequence)
        sequence_occurrences[seq_hash].append((sequence, run_id))

    # Filter by min_occurrences and build result
    patterns: list[dict[str, object]] = []
    for seq_hash, occurrences in sequence_occurrences.items():
        if len(occurrences) < min_occurrences:
            continue
        sequence = occurrences[0][0]
        run_ids = [occ[1] for occ in occurrences]
        confidence = min(1.0, len(occurrences) / 10.0)
        patterns.append({
            "sequence": sequence,
            "occurrences": len(occurrences),
            "run_ids": run_ids,
            "confidence": confidence,
        })

    return patterns


def auto_propose_skill(
    project_dir: str,
    pattern: dict[str, object],
) -> dict[str, object] | None:
    """Create a skill proposal for a qualifying pattern."""
    sequence = pattern.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        return None

    evidence_runs = pattern.get("run_ids")
    if not isinstance(evidence_runs, list):
        evidence_runs = []

    occurrences = int(pattern.get("occurrences", 0))
    if occurrences < 3:
        return None

    # Check if already proposed by looking for existing proposals with same sequence
    sequence_hash = _hash_sequence([str(s) for s in sequence])
    proposals_dir = _proposal_dir_for_project(project_dir)
    if proposals_dir.exists():
        for proposal_file in proposals_dir.glob("proposal-*.json"):
            if proposal_file.name.endswith("-eval.json") or proposal_file.name.endswith("-promoted.json"):
                continue
            try:
                proposal_data = json.loads(proposal_file.read_text(encoding="utf-8"))
                existing_metadata = proposal_data.get("metadata", {})
                if isinstance(existing_metadata, dict):
                    existing_hash = existing_metadata.get("sequence_hash")
                    if existing_hash == sequence_hash:
                        return None  # Already proposed
            except (OSError, json.JSONDecodeError):
                continue

    # Create proposal
    name = f"workflow/{'-'.join(str(s) for s in sequence[:3])}"
    if len(sequence) > 3:
        name += f"-and-{len(sequence) - 3}-more"

    # Temporarily set project dir for propose_skill
    old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        proposal = propose_skill(
            name=name,
            source="auto_detected",
            description=f"Auto-detected workflow with {occurrences} successful executions",
            metadata={
                "sequence": sequence,
                "sequence_hash": sequence_hash,
                "occurrences": occurrences,
                "evidence_runs": evidence_runs,
                "confidence": pattern.get("confidence", 0.0),
            },
        )
    finally:
        if old_project_dir is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = old_project_dir
        else:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)

    # Add evidence_runs to the returned proposal
    proposal["evidence_runs"] = evidence_runs
    return proposal


# -----------------------------------------------------------------------------
# NF6b: Evidence-of-success linking
# -----------------------------------------------------------------------------


def get_proposal_evidence_summary(
    proposal_id: str,
    project_dir: str,
) -> dict[str, object]:
    """Return summary of evidence runs for a proposal."""
    normalized_id = str(proposal_id).strip()

    # Read proposal to get evidence_runs
    proposals_dir = _proposal_dir_for_project(project_dir)
    proposal_path = proposals_dir / f"{normalized_id}.json"

    evidence_runs: list[str] = []
    if proposal_path.exists():
        try:
            proposal_data = json.loads(proposal_path.read_text(encoding="utf-8"))
            metadata = proposal_data.get("metadata", {})
            if isinstance(metadata, dict):
                runs = metadata.get("evidence_runs")
                if isinstance(runs, list):
                    evidence_runs = [str(r) for r in runs if str(r).strip()]
        except (OSError, json.JSONDecodeError):
            pass

    if not evidence_runs:
        return {
            "total_runs": 0,
            "passing_runs": 0,
            "failing_runs": 0,
            "verdict": "review",
        }

    # Check each run's proof_gate verdict
    passing_runs = 0
    failing_runs = 0

    for run_id in evidence_runs:
        verdict = _get_run_verdict(project_dir, run_id)
        if verdict == "pass":
            passing_runs += 1
        elif verdict == "fail":
            failing_runs += 1
        # Unknown verdicts are neither passing nor failing

    total_runs = len(evidence_runs)

    # Determine overall verdict
    if failing_runs > 0:
        verdict = "reject"
    elif passing_runs == total_runs and total_runs > 0:
        verdict = "promote"
    else:
        verdict = "review"

    return {
        "total_runs": total_runs,
        "passing_runs": passing_runs,
        "failing_runs": failing_runs,
        "verdict": verdict,
    }


def _get_run_verdict(project_dir: str, run_id: str) -> str:
    """Get the proof_gate verdict for a given run_id."""
    # Look for evaluation files that reference this run_id
    # Check in skill-proposals directory for eval files
    proposals_dir = _proposal_dir_for_project(project_dir)
    if not proposals_dir.exists():
        return "unknown"

    for eval_file in proposals_dir.glob("*-eval.json"):
        try:
            eval_data = json.loads(eval_file.read_text(encoding="utf-8"))
            proof_gate_result = eval_data.get("proof_gate_result", {})
            if isinstance(proof_gate_result, dict):
                evidence_summary = proof_gate_result.get("evidence_summary", {})
                if isinstance(evidence_summary, dict):
                    if evidence_summary.get("run_id") == run_id:
                        return str(proof_gate_result.get("verdict", "unknown"))
        except (OSError, json.JSONDecodeError):
            continue

    # Also check run verdicts stored separately
    verdicts_dir = Path(project_dir) / ".omg" / "state" / "skill_registry" / "run_verdicts"
    verdict_path = verdicts_dir / f"{run_id}.json"
    if verdict_path.exists():
        try:
            verdict_data = json.loads(verdict_path.read_text(encoding="utf-8"))
            return str(verdict_data.get("verdict", "unknown"))
        except (OSError, json.JSONDecodeError):
            pass

    return "unknown"


def record_run_verdict(project_dir: str, run_id: str, verdict: str) -> None:
    """Record a proof_gate verdict for a run_id."""
    normalized_run_id = str(run_id).strip()
    normalized_verdict = str(verdict).strip().lower()
    if not normalized_run_id:
        return

    verdicts_dir = Path(project_dir) / ".omg" / "state" / "skill_registry" / "run_verdicts"
    verdicts_dir.mkdir(parents=True, exist_ok=True)

    verdict_path = verdicts_dir / f"{normalized_run_id}.json"
    payload = {
        "run_id": normalized_run_id,
        "verdict": normalized_verdict,
        "ts": _timestamp(),
    }
    temp_path = verdict_path.with_name(f"{verdict_path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    os.replace(temp_path, verdict_path)


def _hash_args(args: dict[str, object]) -> str:
    """Create a deterministic hash of args dict."""
    try:
        serialized = json.dumps(args, sort_keys=True, ensure_ascii=True)
    except (TypeError, ValueError):
        serialized = str(args)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _hash_sequence(sequence: list[str]) -> str:
    """Create a deterministic hash of a tool sequence."""
    serialized = json.dumps(sequence, ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _workflow_log_path(project_dir: str) -> Path:
    return Path(project_dir) / ".omg" / "state" / "skill_registry" / "workflow-log.jsonl"


def _proposal_dir_for_project(project_dir: str) -> Path:
    return Path(project_dir) / ".omg" / "state" / "skill-proposals"
