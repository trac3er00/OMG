"""Mutation safety gate for runtime tool and command execution.

This module classifies tool requests by mutation capability and enforces OMG
policy preconditions before write-capable operations are allowed. It verifies
governance context, active test-intent locks, tool-plan presence, and done-when
compliance, then emits deterministic allow/blocked/exempt decisions with
warning/block artifacts under ``.omg/state/mutation_gate``.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from runtime.release_run_coordinator import get_active_coordinator_run_id, is_release_orchestration_active, resolve_current_run_id
from runtime.test_intent_lock import verify_done_when, verify_lock
from runtime.tool_plan_gate import has_tool_plan_for_run


_MUTATING_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})
_EXEMPTIONS = frozenset({"docs", "config", "generated", "test"})
_MUTATION_BASH_PATTERNS = (
    r"\b(git\s+(add|commit|push|rebase|cherry-pick|merge|tag(?!\s+(-l|--list)\b)))\b",
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
_SHELL_C_PATTERN = re.compile(r"\b(?:bash|sh|zsh)\s+-[^\s]*c\s+([\"'])(.+?)\1")
_FULLY_QUOTED_PATTERN = re.compile(r"^\s*([\"']).*\1\s*$")
_READ_ONLY_BASH_ALLOWLIST = (
    re.compile(r"^python\d?(?:\s+-[vV]{1,2}|\s+--version)(?:\s|$)"),
    re.compile(r"^git\s+status(?:\s|$)"),
    re.compile(r"^gh\s+pr\s+view(?:\s|$)"),
    re.compile(r"^(?:.+\|\s*)?tee\s+/dev/null(?:\s|$)"),
)
_QUOTED_SEGMENT_PATTERN = re.compile(r"(['\"]).*?\1")


def check_mutation_allowed(
    tool: str,
    file_path: str,
    project_dir: str,
    lock_id: str | None,
    *,
    exemption: str | None = None,
    command: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, str | None]:
    """Evaluate whether a tool invocation is permitted to mutate state.

    The gate first resolves exemptions and mutation capability, then enforces
    release bypass, governance context, test-intent lock verification,
    run-scoped tool plan presence, and done-when constraints. In permissive mode
    it warns and allows; in strict mode it blocks and writes a block artifact.

    Args:
        tool: Tool name being invoked (for example ``Edit`` or ``Bash``).
        file_path: Target file path associated with the operation.
        project_dir: Project root used for state and artifact paths.
        lock_id: Optional test-intent lock identifier supplied by the caller.
        exemption: Optional exemption token (docs/config/generated/test).
        command: Optional command payload used for Bash mutation detection.
        run_id: Optional run identifier used to resolve lock and plan state.
        metadata: Optional governance metadata, including explicit exemption and
            done-when payload.

    Returns:
        Decision payload containing ``status``, ``reason``, and resolved
        ``lock_id``.
    """
    normalized_tool = str(tool or "").strip()
    normalized_file_path = str(file_path or "").strip()
    normalized_lock_id = str(lock_id or "").strip() or None
    normalized_exemption = str(exemption or "").strip().lower() or None
    normalized_command = str(command or "").strip()
    metadata_obj = metadata if isinstance(metadata, dict) else {}
    explicit_exempt = bool(metadata_obj.get("exempt") is True)
    strict_mode = os.environ.get("OMG_TDD_GATE_STRICT", "1").strip() != "0"

    if explicit_exempt and (normalized_exemption in _EXEMPTIONS or metadata_obj.get("exempt_reason")):
        return {
            "status": "exempt",
            "reason": "metadata exemption allows mutation without lock",
            "lock_id": normalized_lock_id,
        }

    if normalized_exemption in _EXEMPTIONS:
        return {
            "status": "exempt",
            "reason": f"exemption '{normalized_exemption}' allows mutation without lock",
            "lock_id": normalized_lock_id,
        }

    requires_lock = normalized_tool in _MUTATING_TOOLS
    if normalized_tool == "Bash":
        requires_lock = _is_mutation_capable_bash(normalized_command)

    if not requires_lock:
        return {
            "status": "allowed",
            "reason": "tool is read-only for mutation gate",
            "lock_id": normalized_lock_id,
        }

    resolved_run_id = (
        get_active_coordinator_run_id(project_dir=project_dir)
        or str(run_id or "").strip()
        or resolve_current_run_id(project_dir=project_dir)
    )

    # Release orchestration bypass: check FIRST before lock/plan/done_when gates.
    # When release orchestration is active, all TDD gates are bypassed to allow
    # CI/release operations to proceed without requiring test-intent locks.
    if is_release_orchestration_active(project_dir=project_dir):
        return {
            "status": "allowed",
            "reason": "release_orchestration_active",
            "lock_id": normalized_lock_id,
        }

    # Governance context check: if there is NO active run context AND no explicit
    # lock_id, there is no governance context at all.  Returning
    # `no_active_test_intent_lock` here would be a false positive — that reason
    # code is reserved for when a run context IS present but the lock lookup
    # fails.  Use `mutation_context_required` instead so callers can distinguish
    # "no governance context" from "context present but lock missing".
    if not resolved_run_id and normalized_lock_id is None:
        if strict_mode:
            _write_block_artifact(project_dir, normalized_tool, normalized_file_path, "mutation_context_required")
            return {
                "status": "blocked",
                "reason": "mutation_context_required",
                "lock_id": None,
            }
        _write_warning_artifact(project_dir, normalized_tool, normalized_file_path, "mutation_context_required")
        warnings.warn(
            f"mutation_gate_permissive_allow:{normalized_tool}:mutation_context_required",
            RuntimeWarning,
            stacklevel=2,
        )
        return {
            "status": "allowed",
            "reason": "mutation_context_required",
            "lock_id": None,
        }

    verification = verify_lock(project_dir, run_id=resolved_run_id, lock_id=normalized_lock_id)
    if verification.get("status") != "ok":
        reason = str(verification.get("reason", "no_active_test_intent_lock"))
        if strict_mode:
            _write_block_artifact(project_dir, normalized_tool, normalized_file_path, reason)
            return {
                "status": "blocked",
                "reason": reason,
                "lock_id": normalized_lock_id,
            }

        _write_warning_artifact(project_dir, normalized_tool, normalized_file_path, reason)
        warnings.warn(
            f"mutation_gate_permissive_allow:{normalized_tool}:{reason}",
            RuntimeWarning,
            stacklevel=2,
        )
        return {
            "status": "allowed",
            "reason": reason,
            "lock_id": normalized_lock_id,
        }

    if resolved_run_id and not has_tool_plan_for_run(project_dir, resolved_run_id):
        reason = "tool_plan_required"
        if strict_mode:
            _write_block_artifact(project_dir, normalized_tool, normalized_file_path, reason)
            return {
                "status": "blocked",
                "reason": reason,
                "lock_id": normalized_lock_id,
            }
        _write_warning_artifact(project_dir, normalized_tool, normalized_file_path, reason)
        warnings.warn(
            f"mutation_gate_permissive_allow:{normalized_tool}:{reason}",
            RuntimeWarning,
            stacklevel=2,
        )
        return {
            "status": "allowed",
            "reason": reason,
            "lock_id": normalized_lock_id,
        }

    if resolved_run_id:
        done_when_verification = verify_done_when(metadata_obj, run_id=resolved_run_id)
        if done_when_verification.get("status") != "ok":
            reason = str(done_when_verification.get("reason", "done_when_required"))
            if strict_mode:
                _write_block_artifact(project_dir, normalized_tool, normalized_file_path, reason)
                return {
                    "status": "blocked",
                    "reason": reason,
                    "lock_id": normalized_lock_id,
                }

            _write_warning_artifact(project_dir, normalized_tool, normalized_file_path, reason)
            warnings.warn(
                f"mutation_gate_permissive_allow:{normalized_tool}:{reason}",
                RuntimeWarning,
                stacklevel=2,
            )
            return {
                "status": "allowed",
                "reason": reason,
                "lock_id": normalized_lock_id,
            }

    return {
        "status": "allowed",
        "reason": "active test intent lock found",
        "lock_id": str(verification.get("lock_id") or normalized_lock_id or "") or None,
    }


def _is_mutation_capable_bash(command: str) -> bool:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return False

    shell_payload = _extract_shell_payload(normalized_command)
    if shell_payload is not None:
        return _is_mutation_capable_bash(shell_payload)

    lowered = _strip_harmless_redirections(normalized_command.lower())
    if _is_allowlisted_read_only_command(lowered):
        return False

    dequoted = _strip_quoted_segments(lowered)
    for pattern in _MUTATION_BASH_PATTERNS:
        if re.search(pattern, dequoted):
            return True
    # File-write redirection: only classify as mutation if the command itself
    # is NOT a known read-only program.  `python3 script.py > out.json` is a
    # read-only computation that merely saves output; the actual mutation
    # patterns (git commit, rm, mv, etc.) are already caught above.
    if _FILE_WRITE_REDIRECTION_PATTERN.search(dequoted):
        if not _is_read_only_program_with_redirect(normalized_command):
            return True
    return False


def _is_read_only_program_with_redirect(command: str) -> bool:
    """Return True when the command before any > redirect is a read-only program."""
    cmd_portion = re.split(r"(?<!\d)\s*>>?\s+\S+", command)[0].strip()
    if not cmd_portion:
        return False
    lowered = cmd_portion.lower()
    _read_only_prefixes = (
        "python", "python3", "node", "ruby", "perl",
        "jq", "yq",
        "git log", "git diff", "git status", "git show", "git branch",
        "gh pr", "gh run", "gh api",
        "ls", "find", "grep", "rg", "ag", "wc", "sort", "uniq",
        "head", "tail", "less", "more", "file", "stat", "du", "df",
        "env", "printenv", "uname", "whoami", "hostname", "date",
    )
    for prefix in _read_only_prefixes:
        if lowered.startswith(prefix):
            return True
    return False


def _strip_harmless_redirections(command: str) -> str:
    sanitized = command
    for pattern in _HARMLESS_REDIRECTION_PATTERNS:
        sanitized = pattern.sub(" ", sanitized)
    return re.sub(r"\s+", " ", sanitized).strip()


def _extract_shell_payload(command: str) -> str | None:
    match = _SHELL_C_PATTERN.search(command.strip())
    if not match:
        return None
    return str(match.group(2)).strip()


def _strip_quoted_segments(command: str) -> str:
    if _FULLY_QUOTED_PATTERN.match(command):
        return ""
    return re.sub(r"\s+", " ", _QUOTED_SEGMENT_PATTERN.sub(" ", command)).strip()


def _is_allowlisted_read_only_command(command: str) -> bool:
    stripped = command.strip()
    if not stripped:
        return True
    if _FULLY_QUOTED_PATTERN.match(stripped):
        return True
    for pattern in _READ_ONLY_BASH_ALLOWLIST:
        if pattern.search(stripped):
            return True
    return False


def _write_warning_artifact(project_dir: str, tool: str, file_path: str, reason: str) -> None:
    state_dir = Path(project_dir) / ".omg" / "state" / "mutation_gate"
    state_dir.mkdir(parents=True, exist_ok=True)

    path_hash = sha256(file_path.encode("utf-8")).hexdigest()[:8]
    artifact_path = state_dir / f"warn-{path_hash}.json"
    payload = {
        "status": "warning",
        "tool": tool,
        "file_path": file_path,
        "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    temp_path = artifact_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temp_path, artifact_path)


def _write_block_artifact(project_dir: str, tool: str, file_path: str, reason: str) -> None:
    state_dir = Path(project_dir) / ".omg" / "state" / "mutation_gate"
    state_dir.mkdir(parents=True, exist_ok=True)

    path_hash = sha256(file_path.encode("utf-8")).hexdigest()[:8]
    artifact_path = state_dir / f"{path_hash}.json"
    payload = {
        "status": "blocked",
        "tool": tool,
        "file_path": file_path,
        "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    temp_path = artifact_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temp_path, artifact_path)
