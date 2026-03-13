from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from registry.approval_artifact import load_approval_artifact_from_path, verify_approval_artifact
from registry.verify_artifact import verify_artifact, verify_tool_attestation
from runtime.claim_judge import evaluate_claims_for_release
from runtime.runtime_contracts import read_run_state


_READ_ONLY_TOOL_HINTS = (
    "read",
    "search",
    "review",
    "grep",
    "glob",
    "list",
    "ls",
)
_MUTATION_TOOLS = frozenset({"write", "edit", "multiedit", "bash"})
_EXTERNAL_EXECUTION_TOOL_HINTS = (
    "context7",
    "websearch",
    "web_search",
    "browser",
    "playwright",
    "chrome-devtools",
)
_EXTERNAL_BASH_PATTERNS = (
    re.compile(r"(?:^|[\s;&|()])(curl|wget)\b"),
    re.compile(r"(?:^|[\s;&|()])(ssh|scp|rsync)\b"),
    re.compile(r"\bgit\s+(clone|fetch|pull)\b"),
)
_MUTATION_BASH_PATTERNS = (
    r"\b(git\s+(add|commit|push|rebase|cherry-pick|merge|tag))\b",
    r"\b(rm|mv|cp|tee|touch|mkdir|rmdir|ln)\b",
    r"\b(sed\s+-i|perl\s+-pi)\b",
    r"\b(chmod|chown)\b",
)
_HARMLESS_REDIRECTION_PATTERNS = (
    re.compile(r"(?:^|[\s;&|()])\d*>>?\s*/dev/(?:null|stdout|stderr)(?=\s|$)"),
    re.compile(r"(?:^|[\s;&|()])\d*>&\d+(?=\s|$)"),
    re.compile(r"(?:^|[\s;&|()])\d*>&-(?=\s|$)"),
)
_FILE_WRITE_REDIRECTION_PATTERN = re.compile(
    r"(?:^|[\s;&|()])\d*>>?(?!\s*(?:/dev/(?:null|stdout|stderr)\b|&\d+\b|&-\b))\s*\S+"
)


def evaluate_tool_compliance(
    *,
    project_dir: str,
    run_id: str,
    tool: str,
    has_tool_plan: bool,
    clarification_status: dict[str, object] | None = None,
    tool_input: dict[str, object] | None = None,
) -> dict[str, object]:
    clarification = _normalized_clarification_status(clarification_status)
    if clarification["requires_clarification"]:
        reason = _clarification_reason(str(clarification["clarification_prompt"]))
        if _is_mutation_capable_tool(tool, tool_input=tool_input):
            return {
                "status": "blocked",
                "authority": "clarification",
                "reason": reason,
                "clarification_status": clarification,
            }
        if _is_external_execution_tool(tool, tool_input=tool_input):
            return {
                "status": "blocked",
                "authority": "clarification",
                "reason": _clarification_external_reason(str(clarification["clarification_prompt"])),
                "clarification_status": clarification,
            }
        if _is_read_search_review_tool(tool, tool_input=tool_input):
            return {
                "status": "allowed",
                "authority": "clarification",
                "reason": "clarification pending; read/search/review tool allowed",
                "clarification_status": clarification,
            }

    if has_tool_plan:
        council = _read_council_verdicts(project_dir, run_id)
        council_verdict = _council_gate_verdict(council)
        if council_verdict["blocked"]:
            return {
                "status": "blocked",
                "authority": "council_verdicts",
                "reason": str(council_verdict["reason"]),
                "council_verdicts": council.get("verdicts", {}),
            }
        return {"status": "allowed", "authority": "tool_plan", "reason": "tool plan present"}

    return {
        "status": "blocked",
        "authority": "tool_plan",
        "reason": "tool plan required before mutation-capable MCP evaluation",
    }


def evaluate_release_compliance(
    *,
    project_dir: str,
    run_id: str,
    release_evidence: dict[str, object] | None,
) -> dict[str, object]:
    artifact_gate = _artifact_gate_decision(release_evidence)
    if artifact_gate["status"] == "blocked":
        return artifact_gate

    artifact_audit: dict[str, object] = {}
    for key in (
        "artifact_alg",
        "artifact_key_id",
        "artifact_subject_sha256",
        "artifact_verdict",
        "approval_authority",
        "approval_reason",
    ):
        if key in artifact_gate:
            artifact_audit[key] = artifact_gate[key]

    council = _read_council_verdicts(project_dir, run_id)
    council_verdict = _council_gate_verdict(council)
    if council_verdict["blocked"]:
        return {
            "status": "blocked",
            "authority": "council_verdicts",
            "reason": str(council_verdict["reason"]),
            "council_verdicts": council.get("verdicts", {}),
        }

    if not isinstance(release_evidence, dict):
        return {
            "status": "blocked",
            "authority": "release",
            "reason": "no release evidence supplied",
            **artifact_audit,
        }

    raw_claims = release_evidence.get("claims")
    claims = raw_claims if isinstance(raw_claims, list) else []
    if claims:
        claim_decision = evaluate_claims_for_release(project_dir=project_dir, run_id=run_id, claims=claims)
        if claim_decision.get("status") == "blocked":
            return {
                "status": "blocked",
                "authority": "claim_judge",
                "reason": str(claim_decision.get("reason", "claim_judge_verdict=unknown")),
                "claim_judge_verdict": str(claim_decision.get("claim_judge_verdict", "")),
            }

    return {
        "status": "allowed",
        "authority": "release",
        "reason": "compliance checks passed",
        **artifact_audit,
    }


def evaluate_governed_tool_request(
    *,
    project_dir: str,
    run_id: str,
    lane_name: str,
    tool: str,
    has_tool_plan: bool,
    attestation_artifact: dict[str, object] | None,
    require_attestation: bool,
    clarification_status: dict[str, object] | None = None,
) -> dict[str, object]:
    plan_decision = evaluate_tool_compliance(
        project_dir=project_dir,
        run_id=run_id,
        tool=tool,
        has_tool_plan=has_tool_plan,
        clarification_status=clarification_status,
    )
    if plan_decision.get("status") == "blocked":
        return plan_decision

    if not require_attestation:
        return {
            "status": "allowed",
            "authority": "governed_tool",
            "reason": "compliance checks passed without attestation requirement",
        }

    attestation_decision = verify_tool_attestation(
        lane_name=lane_name,
        tool_name=tool,
        artifact=attestation_artifact,
        mode="warn_and_run",
    )
    if attestation_decision.get("status") == "blocked":
        return {
            "status": "blocked",
            "authority": "artifact",
            "reason": str(attestation_decision.get("reason", "attestation required")),
        }
    return {
        "status": "allowed",
        "authority": "governed_tool",
        "reason": "compliance checks passed",
    }


_UNVERIFIED_ARTIFACT_STATUSES = frozenset({"pending_verification", "insufficient_evidence", "placeholder"})


def _artifact_gate_decision(release_evidence: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(release_evidence, dict):
        return {"status": "blocked", "authority": "artifact", "reason": "no release evidence supplied"}
    artifact = release_evidence.get("artifact")
    if not isinstance(artifact, dict):
        return {"status": "blocked", "authority": "artifact", "reason": "no artifact supplied"}

    artifact_contracts = artifact.get("artifact_contracts")
    if isinstance(artifact_contracts, Mapping):
        unverified = []
        for name, contract in artifact_contracts.items():
            if isinstance(contract, Mapping):
                status = str(contract.get("status", "")).strip().lower()
                if status in _UNVERIFIED_ARTIFACT_STATUSES:
                    unverified.append(f"{name}={status}")
        if unverified:
            return {
                "status": "blocked",
                "authority": "artifact",
                "reason": f"artifact_contracts contain unverified artifacts: {', '.join(unverified)}",
            }

    verified = verify_artifact(artifact)
    action = str(verified.get("action", "")).strip().lower()
    audit_fields = {
        "artifact_alg": str(verified.get("algorithm", "")),
        "artifact_key_id": str(verified.get("key_id", "")),
        "artifact_subject_sha256": str(verified.get("subject_sha256", "")),
        "artifact_verdict": str(verified.get("action", "")),
    }

    if action == "deny":
        return {
            "status": "blocked",
            "authority": "artifact",
            "reason": f"artifact_verification={verified.get('reason', 'denied')}",
        }
    if action == "allow":
        return {
            "status": "allowed",
            "authority": "artifact",
            "reason": f"artifact_verification={verified.get('action', 'allow')}",
            **audit_fields,
        }
    if action == "ask":
        expected_digest = audit_fields["artifact_subject_sha256"]
        approval_artifact = release_evidence.get("approval_artifact")
        if isinstance(approval_artifact, dict):
            approval_result = verify_approval_artifact(approval_artifact, expected_artifact_digest=expected_digest)
            if bool(approval_result.get("valid")):
                return {
                    "status": "allowed",
                    "authority": "artifact",
                    "reason": "artifact_verification=ask; approval artifact verified",
                    "approval_authority": str(approval_artifact.get("signer_key_id", "")),
                    "approval_reason": str(approval_artifact.get("reason", "")),
                    **audit_fields,
                }

        approval_path = release_evidence.get("approval_artifact_path")
        if isinstance(approval_path, str) and approval_path.strip():
            loaded = load_approval_artifact_from_path(
                approval_path.strip(),
                expected_artifact_digest=expected_digest,
            )
            if bool(loaded.get("valid")):
                approval_payload = loaded.get("approval")
                approval_dict = approval_payload if isinstance(approval_payload, dict) else {}
                return {
                    "status": "allowed",
                    "authority": "artifact",
                    "reason": "artifact_verification=ask; approval artifact verified",
                    "approval_authority": str(approval_dict.get("signer_key_id", "")),
                    "approval_reason": str(approval_dict.get("reason", "")),
                    **audit_fields,
                }

        return {
            "status": "blocked",
            "authority": "artifact",
            "reason": "ask result requires signed approval artifact",
        }

    return {
        "status": "blocked",
        "authority": "artifact",
        "reason": "unknown artifact verification action",
    }


def _read_council_verdicts(project_dir: str, run_id: str | None) -> dict[str, object]:
    if not run_id:
        return {}
    payload = read_run_state(project_dir, "council_verdicts", run_id)
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _council_gate_verdict(council: dict[str, object]) -> dict[str, object]:
    verdicts = council.get("verdicts")
    if not isinstance(verdicts, Mapping):
        return {"blocked": False, "reason": ""}

    for critic_name, critic_payload in verdicts.items():
        if not isinstance(critic_payload, Mapping):
            continue
        token = str(critic_payload.get("verdict", "")).strip().lower()
        if token == "fail":
            return {
                "blocked": True,
                "reason": f"council critic '{critic_name}' failed; block mutation-capable tool execution",
            }
    return {"blocked": False, "reason": ""}


def _normalized_clarification_status(clarification_status: dict[str, object] | None) -> dict[str, object]:
    raw = clarification_status if isinstance(clarification_status, dict) else {}
    prompt = str(raw.get("clarification_prompt", "")).strip().replace("\n", " ")
    confidence = _to_float(raw.get("confidence"), 0.0)
    return {
        "requires_clarification": bool(raw.get("requires_clarification") is True),
        "intent_class": str(raw.get("intent_class", "")).strip(),
        "clarification_prompt": prompt,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
    }


def _clarification_reason(clarification_prompt: str) -> str:
    prompt = " ".join(str(clarification_prompt or "").split())
    if prompt:
        return f"Clarification required before mutation: {prompt}"
    return "Clarification required before mutation: provide the missing intent details."


def _clarification_external_reason(clarification_prompt: str) -> str:
    prompt = " ".join(str(clarification_prompt or "").split())
    if prompt:
        return f"Clarification required before external execution: {prompt}"
    return "Clarification required before external execution: provide the missing intent details."


def classify_bash_command_mode(command: str) -> str:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return "read"
    if _is_mutation_capable_bash(normalized_command):
        return "mutation"
    lowered = normalized_command.lower()
    for pattern in _EXTERNAL_BASH_PATTERNS:
        if pattern.search(lowered):
            return "external"
    return "read"


def _is_mutation_capable_bash(command: str) -> bool:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return False
    lowered = _strip_harmless_redirections(normalized_command.lower())
    for pattern in _MUTATION_BASH_PATTERNS:
        if re.search(pattern, lowered):
            return True
    if _FILE_WRITE_REDIRECTION_PATTERN.search(lowered):
        return True
    return False


def _strip_harmless_redirections(command: str) -> str:
    sanitized = command
    for pattern in _HARMLESS_REDIRECTION_PATTERNS:
        sanitized = pattern.sub(" ", sanitized)
    return re.sub(r"\s+", " ", sanitized).strip()


def _is_mutation_capable_tool(tool: str, *, tool_input: dict[str, object] | None = None) -> bool:
    token = str(tool or "").strip().lower()
    if token == "bash":
        mode = classify_bash_command_mode(str((tool_input or {}).get("command", "")))
        return mode == "mutation"
    if token in _MUTATION_TOOLS:
        return True
    return token == "bash:mutation"


def _is_external_execution_tool(tool: str, *, tool_input: dict[str, object] | None = None) -> bool:
    token = str(tool or "").strip().lower()
    if token == "bash":
        mode = classify_bash_command_mode(str((tool_input or {}).get("command", "")))
        return mode == "external"
    if token == "bash:external":
        return True
    return any(hint in token for hint in _EXTERNAL_EXECUTION_TOOL_HINTS)


def _is_read_search_review_tool(tool: str, *, tool_input: dict[str, object] | None = None) -> bool:
    token = str(tool or "").strip().lower()
    if not token:
        return False
    if token == "bash":
        mode = classify_bash_command_mode(str((tool_input or {}).get("command", "")))
        return mode == "read"
    return any(hint in token for hint in _READ_ONLY_TOOL_HINTS)


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
