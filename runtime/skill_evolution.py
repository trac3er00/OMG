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
    proposal_id: str, test_results: dict[str, object]
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
    proof_gate_result = cast(
        dict[str, object], proof_gate.evaluate_proof_gate(gate_input)
    )
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
