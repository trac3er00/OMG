from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, NamedTuple, cast

from runtime import proof_gate


def propose_skill(
    name: str,
    source: str,
    description: str = "",
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
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
    if project_dir is not None:
        proposal_path = _foundry_proposal_path(project_dir, normalized_id)
        proposal_payload = _read_json(proposal_path)
    else:
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
    proof_gate_result = cast(
        dict[str, object], proof_gate.evaluate_proof_gate(gate_input)
    )
    if project_dir is not None:
        evidence_check = _check_evidence_runs(project_dir, proposal_payload)
        existing_blockers = proof_gate_result.get("blockers")
        blockers_list: list[str] = (
            list(cast(list[object], existing_blockers))  # type: ignore[arg-type]
            if isinstance(existing_blockers, list)
            else []
        )
        if evidence_check["has_failure"]:
            if "evidence_run_failed" not in blockers_list:
                blockers_list.append("evidence_run_failed")
            proof_gate_result["verdict"] = "fail"
        proof_gate_result["blockers"] = blockers_list
        existing_summary = proof_gate_result.get("evidence_summary")
        summary_dict: dict[str, object] = (
            dict(cast(Mapping[str, object], existing_summary))
            if isinstance(existing_summary, dict)
            else {}
        )
        summary_dict["evidence_runs_verified"] = (
            not evidence_check["has_failure"] and not evidence_check["has_unknown"]
        )
        summary_dict["evidence_runs_count"] = evidence_check["total_runs"]
        proof_gate_result["evidence_summary"] = summary_dict
    promotable = str(proof_gate_result.get("verdict", "fail")) == "pass"
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


def _build_proof_gate_input(
    proposal_id: str, test_results: dict[str, object]
) -> dict[str, object]:
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
    eval_output = (
        cast(dict[str, object], dict(raw_eval_output))
        if isinstance(raw_eval_output, dict)
        else {}
    )

    raw_security_evidence = test_results.get("security_evidence")
    security_evidence = (
        cast(dict[str, object], dict(raw_security_evidence))
        if isinstance(raw_security_evidence, dict)
        else {}
    )

    raw_browser_evidence = test_results.get("browser_evidence")
    browser_evidence = (
        cast(dict[str, object], dict(raw_browser_evidence))
        if isinstance(raw_browser_evidence, dict)
        else {}
    )

    raw_claims = test_results.get("claims")
    claims = list(raw_claims) if isinstance(raw_claims, list) else []

    raw_evidence_pack = test_results.get("evidence_pack")
    evidence_pack: dict[str, object] = (
        cast(dict[str, object], dict(raw_evidence_pack))
        if isinstance(raw_evidence_pack, dict)
        else {}
    )
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


class ToolSequence(NamedTuple):
    tools: tuple[str, ...]

    def __len__(self) -> int:  # type: ignore[override]
        return len(self.tools)


class SkillProposal:
    def __init__(
        self,
        name: str,
        trigger: str,
        tool_sequence: ToolSequence,
        expected_outcome: str,
    ) -> None:
        self.name = name
        self.trigger = trigger
        self.tool_sequence = tool_sequence
        self.expected_outcome = expected_outcome
        self.occurrence_count: int = 0
        self.status: str = "proposed"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "tool_sequence": list(self.tool_sequence.tools),
            "expected_outcome": self.expected_outcome,
            "occurrence_count": self.occurrence_count,
            "status": self.status,
        }


def detect_repeated_patterns(
    session_histories: list[list[str]],
    min_sequence_length: int = 3,
    min_occurrences: int = 3,
) -> list[tuple[ToolSequence, int]]:
    sequence_counts: Counter[ToolSequence] = Counter()

    for session in session_histories:
        for start in range(len(session)):
            for end in range(start + min_sequence_length, len(session) + 1):
                seq = ToolSequence(tuple(session[start:end]))
                sequence_counts[seq] += 1

    repeated = [
        (seq, count)
        for seq, count in sequence_counts.items()
        if count >= min_occurrences
    ]
    return sorted(repeated, key=lambda x: x[1], reverse=True)


def auto_propose_skill(
    sequence: ToolSequence,
    occurrence_count: int,
) -> SkillProposal:
    tool_names = list(sequence.tools)
    name = f"auto-{'-'.join(tool_names[:3])}"
    trigger = f"When needing to {tool_names[0]} followed by {tool_names[-1]}"
    outcome = f"Automated sequence: {' → '.join(tool_names)}"

    proposal = SkillProposal(
        name=name,
        trigger=trigger,
        tool_sequence=sequence,
        expected_outcome=outcome,
    )
    proposal.occurrence_count = occurrence_count
    return proposal


def save_skill_proposal(
    proposal: SkillProposal,
    proposals_dir: str = ".omg/skill-proposals",
) -> str:
    os.makedirs(proposals_dir, exist_ok=True)
    filename = f"{proposal.name}.json"
    filepath = os.path.join(proposals_dir, filename)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(proposal.to_dict(), fh, indent=2, ensure_ascii=True)
    return filepath


def run_auto_propose(
    session_histories: list[list[str]],
    proposals_dir: str = ".omg/skill-proposals",
    min_sequence_length: int = 3,
    min_occurrences: int = 3,
) -> list[SkillProposal]:
    patterns = detect_repeated_patterns(
        session_histories,
        min_sequence_length,
        min_occurrences,
    )
    proposals: list[SkillProposal] = []
    for sequence, count in patterns:
        proposal = auto_propose_skill(sequence, count)
        save_skill_proposal(proposal, proposals_dir)
        proposals.append(proposal)
    return proposals


class SkillHealthMetrics:
    """Track skill usage and success metrics."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        self.usage_count = 0
        self.success_count = 0
        self.consecutive_failures = 0
        self.failure_reasons: list[str] = []

    def record_success(self) -> None:
        self.usage_count += 1
        self.success_count += 1
        self.consecutive_failures = 0

    def record_failure(self, reason: str = "") -> None:
        self.usage_count += 1
        self.consecutive_failures += 1
        if reason:
            self.failure_reasons.append(reason)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.usage_count if self.usage_count > 0 else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "skill_name": self.skill_name,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": self.success_rate,
        }


class SkillLifecycleManager:
    """Manages skill promotion and retirement lifecycle."""

    def __init__(
        self,
        promote_after_successes: int = 5,
        retire_after_failures: int = 3,
        proposals_dir: str = ".omg/skill-proposals",
    ) -> None:
        self.promote_after_successes = promote_after_successes
        self.retire_after_failures = retire_after_failures
        self.proposals_dir = proposals_dir
        self.metrics: dict[str, SkillHealthMetrics] = {}

    def get_metrics(self, skill_name: str) -> SkillHealthMetrics:
        if skill_name not in self.metrics:
            self.metrics[skill_name] = SkillHealthMetrics(skill_name)
        return self.metrics[skill_name]

    def record_use(self, skill_name: str, success: bool, reason: str = "") -> str:
        """Record a skill use. Returns new status: 'proposed', 'active', 'retired'."""
        m = self.get_metrics(skill_name)
        if success:
            m.record_success()
        else:
            m.record_failure(reason)

        if m.success_count >= self.promote_after_successes:
            self._update_skill_status(skill_name, "active")
            return "active"

        if m.consecutive_failures >= self.retire_after_failures:
            self._update_skill_status(skill_name, "retired")
            return "retired"

        return "proposed"

    def _update_skill_status(self, skill_name: str, new_status: str) -> None:
        import glob as _glob

        pattern = os.path.join(self.proposals_dir, f"*{skill_name}*.json")
        for filepath in _glob.glob(pattern):
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                data["status"] = new_status
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=True)
            except Exception:
                pass


import hashlib


def _foundry_registry_dir(project_dir: str) -> Path:
    return Path(project_dir) / ".omg" / "state" / "skill_registry"


def _foundry_workflow_log(project_dir: str) -> Path:
    return _foundry_registry_dir(project_dir) / "workflow-log.jsonl"


def _foundry_proposals_dir(project_dir: str) -> Path:
    return _foundry_registry_dir(project_dir) / "proposals"


def _foundry_proposal_path(project_dir: str, proposal_id: str) -> Path:
    return _foundry_proposals_dir(project_dir) / f"{proposal_id}.json"


def _foundry_verdicts_path(project_dir: str) -> Path:
    return _foundry_registry_dir(project_dir) / "run-verdicts.json"


def _hash_args(args: Mapping[str, object]) -> str:
    try:
        normalized = json.dumps(args, sort_keys=True, default=str)
    except (TypeError, ValueError):
        normalized = repr(args)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def record_workflow_step(
    project_dir: str,
    tool_name: str,
    args: Mapping[str, object],
    success: bool,
    run_id: str,
) -> None:
    tool = str(tool_name).strip()
    run = str(run_id).strip()
    if not tool or not run:
        return
    log_path = _foundry_workflow_log(project_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry: dict[str, object] = {
        "tool": tool,
        "args_hash": _hash_args(args),
        "success": bool(success),
        "run_id": run,
        "ts": _timestamp(),
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def detect_reusable_patterns(
    project_dir: str,
    min_occurrences: int = 3,
) -> list[dict[str, object]]:
    log_path = _foundry_workflow_log(project_dir)
    if not log_path.exists():
        return []

    runs: dict[str, list[dict[str, object]]] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        run_id = str(entry.get("run_id") or "").strip()
        if not run_id:
            continue
        runs.setdefault(run_id, []).append(entry)

    successful_sequences: dict[tuple[str, ...], list[str]] = {}
    for run_id, entries in runs.items():
        if not entries or not all(bool(e.get("success")) for e in entries):
            continue
        tools = tuple(str(e.get("tool") or "") for e in entries)
        if not all(tools):
            continue
        successful_sequences.setdefault(tools, []).append(run_id)

    total_steps = sum(len(entries) for entries in runs.values())
    patterns: list[dict[str, object]] = []
    for tools, run_ids in successful_sequences.items():
        if len(run_ids) < min_occurrences:
            continue
        confidence = len(run_ids) / total_steps if total_steps else 0.0
        patterns.append(
            {
                "sequence": list(tools),
                "occurrences": len(run_ids),
                "run_ids": list(run_ids),
                "confidence": round(confidence, 4),
            }
        )
    patterns.sort(key=lambda p: cast(int, p["occurrences"]), reverse=True)
    return patterns


_ORIGINAL_AUTO_PROPOSE = auto_propose_skill


def auto_propose_skill(*args: object, **kwargs: object) -> object:  # type: ignore[no-redef]
    if args and isinstance(args[0], str) and len(args) >= 2 and isinstance(args[1], dict):
        project_dir = cast(str, args[0])
        pattern = cast(dict[str, object], args[1])
        return _foundry_auto_propose(project_dir, pattern)
    return _ORIGINAL_AUTO_PROPOSE(*args, **kwargs)  # type: ignore[arg-type]


def _foundry_auto_propose(
    project_dir: str,
    pattern: Mapping[str, object],
) -> dict[str, object] | None:
    sequence_raw = pattern.get("sequence")
    if not isinstance(sequence_raw, list) or not sequence_raw:
        return None
    sequence = [str(s) for s in sequence_raw if str(s)]
    if not sequence:
        return None
    occurrences_raw = pattern.get("occurrences", 0)
    occurrences = int(occurrences_raw) if isinstance(occurrences_raw, (int, float)) else 0
    if occurrences < 3:
        return None
    run_ids_raw = pattern.get("run_ids", [])
    run_ids = [str(r) for r in run_ids_raw if isinstance(run_ids_raw, list)] if isinstance(run_ids_raw, list) else []

    proposals_dir = _foundry_proposals_dir(project_dir)
    proposals_dir.mkdir(parents=True, exist_ok=True)
    name = "workflow/" + "-".join(sequence[:3])
    for existing in proposals_dir.glob("*.json"):
        existing_payload = _read_json(existing)
        if existing_payload and existing_payload.get("name") == name:
            return None

    proposal_id = f"wf-{uuid.uuid4().hex[:10]}"
    confidence_raw = pattern.get("confidence", 0.0)
    confidence_val = (
        float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.0
    )
    proposal_payload: dict[str, object] = {
        "schema": "SkillProposal",
        "schema_version": 1,
        "proposal_id": proposal_id,
        "name": name,
        "status": "proposed",
        "source": "auto_detected",
        "sequence": sequence,
        "occurrences": occurrences,
        "run_ids": run_ids,
        "evidence_runs": run_ids,
        "confidence": confidence_val,
        "created_at": _timestamp(),
    }
    _atomic_write_json(_foundry_proposal_path(project_dir, proposal_id), proposal_payload)
    return proposal_payload


def record_run_verdict(project_dir: str, run_id: str, verdict: str) -> None:
    rid = str(run_id).strip()
    v = str(verdict).strip().lower()
    if not rid or v not in {"pass", "fail"}:
        return
    path = _foundry_verdicts_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_json(path) or {}
    existing[rid] = v
    _atomic_write_json(path, existing)


def get_proposal_evidence_summary(
    proposal_id: str, project_dir: str
) -> dict[str, object]:
    proposal = _read_json(_foundry_proposal_path(project_dir, proposal_id))
    if not proposal:
        return {
            "total_runs": 0,
            "passing_runs": 0,
            "failing_runs": 0,
            "verdict": "review",
        }
    evidence_runs_raw = proposal.get("evidence_runs") or proposal.get("run_ids") or []
    evidence_runs = [str(r) for r in evidence_runs_raw] if isinstance(evidence_runs_raw, list) else []
    verdicts = _read_json(_foundry_verdicts_path(project_dir)) or {}
    passing = sum(1 for r in evidence_runs if verdicts.get(r) == "pass")
    failing = sum(1 for r in evidence_runs if verdicts.get(r) == "fail")
    total = len(evidence_runs)
    if failing > 0:
        verdict = "reject"
    elif passing == total and total > 0:
        verdict = "promote"
    else:
        verdict = "review"
    return {
        "total_runs": total,
        "passing_runs": passing,
        "failing_runs": failing,
        "verdict": verdict,
    }


def _check_evidence_runs(
    project_dir: str, proposal_payload: Mapping[str, object]
) -> dict[str, object]:
    evidence_runs_raw = proposal_payload.get("evidence_runs") or proposal_payload.get("run_ids") or []
    evidence_runs = [str(r) for r in evidence_runs_raw] if isinstance(evidence_runs_raw, list) else []
    verdicts = _read_json(_foundry_verdicts_path(project_dir)) or {}
    has_failure = any(verdicts.get(r) == "fail" for r in evidence_runs)
    has_unknown = any(r not in verdicts for r in evidence_runs)
    return {
        "total_runs": len(evidence_runs),
        "has_failure": has_failure,
        "has_unknown": has_unknown,
    }
