"""Bounded context engine — composes per-run context packets.

Reads architecture signals, defense state, verification pointers, and
context pressure into a compact packet with artifact pointers (never raw
content), delta-only refresh support, and explicit budget limits.

Crash-isolated: ``build_packet`` never raises.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from runtime.forge_run_id import build_deterministic_contract
from runtime.memory_store import MemoryStore
from runtime.profile_io import profile_version_from_map

_MAX_SUMMARY_CHARS = 1000
_MAX_CLARIFICATION_PROMPT_CHARS = 180
_PROFILE_SUMMARY_MAX_CHARS = 120
_PROFILE_DIGEST_TAG_MAX = 5
_PROFILE_DIGEST_ARCH_MAX = 3
_PROFILE_DIGEST_CONSTRAINT_MAX = 5
_PACKET_REL_PATH = Path(".omg") / "state" / "context_engine_packet.json"
_PROFILE_REL_PATH = Path(".omg") / "state" / "profile.yaml"
_MEMORY_STORE_REL_PATH = Path(".omg") / "state" / "memory.sqlite3"
_RELEASE_COORDINATOR_REL_BASE = Path(".omg") / "state" / "release_run_coordinator"
_SESSION_REL_PATH = Path(".omg") / "state" / "session.json"
_SNAPSHOTS_REL_BASE = Path(".omg") / "state" / "snapshots"
_CONTEXT_PACKET_KIND = "context_engine_v2_packet"
_CONTEXT_PACKET_SUMMARY = "governed context packet index"
_PACKET_VERSION = "v2"
_MAX_PROVENANCE_POINTERS = 24

_STATE_PATHS = {
    "architecture_signal": Path(".omg") / "state" / "architecture_signal" / "latest.json",
    "defense_state": Path(".omg") / "state" / "defense_state" / "current.json",
    "background_verification": Path(".omg") / "state" / "background-verification.json",
    "context_pressure": Path(".omg") / "state" / ".context-pressure.json",
}
_COUNCIL_REL_BASE = Path(".omg") / "state" / "council_verdicts"
_INTENT_GATE_REL_BASE = Path(".omg") / "state" / "intent_gate"


# ---------------------------------------------------------------------------
# NF3a: One-task-per-session guard
# ---------------------------------------------------------------------------


def get_active_task(project_dir: str) -> dict[str, Any] | None:
    """Read session.json and extract the task_focus field.

    Returns:
        {"task": str, "started_at": str, "files_touched": list} or None if no active task.
    """
    root = Path(project_dir)
    session_path = root / _SESSION_REL_PATH
    if not session_path.exists():
        return None

    try:
        raw = session_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    task_focus = data.get("task_focus")
    if not isinstance(task_focus, dict):
        return None

    task = task_focus.get("task")
    if not task or not isinstance(task, str):
        return None

    return {
        "task": str(task),
        "started_at": str(task_focus.get("started_at", "")),
        "files_touched": list(task_focus.get("files_touched", [])) if isinstance(task_focus.get("files_touched"), list) else [],
    }


def detect_task_drift(current_prompt: str, active_task: dict[str, Any] | None) -> dict[str, Any]:
    """Detect if the current prompt represents a new task vs continuing the active one.

    Simple heuristic: if no words from the active task description appear in the prompt,
    it might be a drift to a new task.

    Returns:
        {"drift": bool, "confidence": float, "active_task": str, "suggested_action": "snapshot|continue"}
    """
    if active_task is None:
        return {"drift": False, "action": "none"}

    task_description = str(active_task.get("task", "")).lower()
    prompt_lower = current_prompt.lower()

    # Extract meaningful words from task (3+ chars, alphanumeric)
    task_words = set(
        word for word in re.findall(r"\b[a-z0-9]{3,}\b", task_description)
        if word not in {"the", "and", "for", "with", "this", "that", "from", "into"}
    )

    if not task_words:
        # No meaningful words to compare
        return {
            "drift": False,
            "confidence": 0.0,
            "active_task": task_description,
            "suggested_action": "continue",
        }

    # Count how many task words appear in the prompt
    matches = sum(1 for word in task_words if word in prompt_lower)
    match_ratio = matches / len(task_words) if task_words else 0.0

    # If less than 20% of task words appear, consider it a potential drift
    drift = match_ratio < 0.2
    confidence = 1.0 - match_ratio  # Higher confidence when fewer matches

    return {
        "drift": drift,
        "confidence": round(confidence, 2),
        "active_task": task_description,
        "suggested_action": "snapshot" if drift else "continue",
    }


def set_task_focus(project_dir: str, task: str, files: list[str] | None = None) -> None:
    """Write task focus to session.json.

    Updates the task_focus field with task description, timestamp, and optional files list.
    """
    root = Path(project_dir)
    session_path = root / _SESSION_REL_PATH

    # Read existing session data or create empty dict
    existing_data: dict[str, Any] = {}
    if session_path.exists():
        try:
            raw = session_path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                existing_data = loaded
        except (OSError, json.JSONDecodeError):
            pass

    # Update task_focus
    existing_data["task_focus"] = {
        "task": task,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "files_touched": files if files is not None else [],
    }

    # Write atomically
    session_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = session_path.with_name(f"{session_path.name}.tmp")
    tmp.write_text(json.dumps(existing_data, indent=2) + "\n", encoding="utf-8")
    os.rename(tmp, session_path)


# ---------------------------------------------------------------------------
# NF3b: Protected handoff snapshot
# ---------------------------------------------------------------------------


def create_handoff_snapshot(project_dir: str) -> str:
    """Create a snapshot for handoff in .omg/state/snapshots/<timestamp>.json.

    Includes: active task, plan state, checklist state, touched files, memory refs.

    Returns:
        The path to the created snapshot file.
    """
    root = Path(project_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = root / _SNAPSHOTS_REL_BASE / f"{ts}.json"

    # Gather active task
    active_task = get_active_task(project_dir)

    # Gather plan state
    plan_path = root / ".omg" / "state" / "_plan.md"
    plan_content: str | None = None
    if plan_path.exists():
        try:
            plan_content = plan_path.read_text(encoding="utf-8")[:4000]
        except OSError:
            pass

    # Gather checklist state
    checklist_path = root / ".omg" / "state" / "_checklist.md"
    checklist_content: str | None = None
    if checklist_path.exists():
        try:
            checklist_content = checklist_path.read_text(encoding="utf-8")[:4000]
        except OSError:
            pass

    # Gather touched files from active task
    files_touched = active_task.get("files_touched", []) if active_task else []

    # Gather memory refs from profile
    profile_digest = load_profile_digest(project_dir)

    snapshot_data = {
        "schema": "HandoffSnapshot",
        "schema_version": "1.0.0",
        "timestamp": ts,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "active_task": active_task,
        "plan_state": plan_content,
        "checklist_state": checklist_content,
        "files_touched": files_touched,
        "memory_refs": {
            "profile_version": profile_digest.get("profile_version", ""),
            "tags": profile_digest.get("tags", []),
        },
    }

    # Write atomically
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = snapshot_path.with_name(f"{snapshot_path.name}.tmp")
    tmp.write_text(json.dumps(snapshot_data, indent=2) + "\n", encoding="utf-8")
    os.rename(tmp, snapshot_path)

    return str(snapshot_path)


def list_handoff_snapshots(project_dir: str) -> list[dict[str, Any]]:
    """List all handoff snapshots with metadata.

    Returns:
        List of dicts with timestamp, task, file_count, sorted by timestamp (newest first).
    """
    root = Path(project_dir)
    snapshots_dir = root / _SNAPSHOTS_REL_BASE

    if not snapshots_dir.exists() or not snapshots_dir.is_dir():
        return []

    result: list[dict[str, Any]] = []

    for entry in snapshots_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue

        try:
            raw = entry.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, dict):
            continue

        active_task = data.get("active_task")
        task_str = ""
        if isinstance(active_task, dict):
            task_str = str(active_task.get("task", ""))

        files_touched = data.get("files_touched", [])
        file_count = len(files_touched) if isinstance(files_touched, list) else 0

        result.append({
            "path": str(entry),
            "timestamp": str(data.get("timestamp", entry.stem)),
            "task": task_str,
            "file_count": file_count,
        })

    # Sort by timestamp descending (newest first)
    result.sort(key=lambda x: x["timestamp"], reverse=True)
    return result


def load_profile_digest(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir)
    profile_path = root / _PROFILE_REL_PATH
    if not profile_path.exists():
        return _empty_profile_digest()

    raw_profile = ""
    parsed: dict[str, Any] = {}
    try:
        raw_profile = profile_path.read_text(encoding="utf-8")
    except OSError:
        return _empty_profile_digest()

    try:
        payload = yaml.safe_load(raw_profile)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        parsed = payload

    digest = _profile_digest_from_map(parsed, raw_profile)
    return digest


def render_profile_digest_text(project_dir: str | Path, *, max_chars: int) -> str:
    digest = load_profile_digest(project_dir)
    arch_items = digest.get("architecture_requests")
    arch_list = arch_items if isinstance(arch_items, list) else []
    arch = ",".join(str(item)[:18] for item in arch_list if str(item).strip())
    constraints_obj = digest.get("constraints", {})
    constraints = constraints_obj if isinstance(constraints_obj, dict) else {}
    constraint_tokens = []
    for key, value in constraints.items():
        if len(constraint_tokens) >= _PROFILE_DIGEST_CONSTRAINT_MAX:
            break
        value_text = str(value).strip()
        if not value_text:
            continue
        constraint_tokens.append(f"{str(key)[:14]}={value_text[:14]}")
    cons = ",".join(constraint_tokens)
    tags_items = digest.get("tags")
    tags_list = tags_items if isinstance(tags_items, list) else []
    tags = ",".join(str(item)[:14] for item in tags_list if str(item).strip())
    try:
        confidence = round(float(digest.get("confidence", 0.0)), 2)
    except (TypeError, ValueError):
        confidence = 0.0
    version = str(digest.get("profile_version", "")).strip()[:24]
    summary = str(digest.get("summary", "")).strip()

    prefix = f"arch[{arch}]|cons[{cons}]|tags[{tags}]|conf={confidence}|ver={version}|sum="
    if len(prefix) >= max_chars:
        return prefix[:max_chars]
    remaining = max_chars - len(prefix)
    if len(summary) > remaining:
        if remaining <= 3:
            summary = summary[:remaining]
        else:
            summary = summary[: remaining - 3] + "..."
    return prefix + summary


def _empty_profile_digest() -> dict[str, Any]:
    return {
        "architecture_requests": [],
        "constraints": {},
        "tags": [],
        "summary": "",
        "confidence": 0.0,
        "profile_version": "",
    }


def _profile_digest_from_map(profile: dict[str, Any], raw_profile: str) -> dict[str, Any]:
    preferences_obj = profile.get("preferences")
    preferences: dict[str, Any] = preferences_obj if isinstance(preferences_obj, dict) else {}
    user_vector_obj = profile.get("user_vector")
    user_vector: dict[str, Any] = user_vector_obj if isinstance(user_vector_obj, dict) else {}
    provenance_obj = profile.get("profile_provenance")
    provenance: dict[str, Any] = provenance_obj if isinstance(provenance_obj, dict) else {}

    architecture_obj = preferences.get("architecture_requests")
    architecture_raw: list[Any] = architecture_obj if isinstance(architecture_obj, list) else []
    architecture_requests = [
        _clean_single_line(item)
        for item in architecture_raw
        if _clean_single_line(item)
    ][:_PROFILE_DIGEST_ARCH_MAX]

    constraints_obj = preferences.get("constraints")
    constraints_raw: dict[str, Any] = constraints_obj if isinstance(constraints_obj, dict) else {}
    constraints = _normalize_constraints(constraints_raw)

    tags_obj = user_vector.get("tags")
    tags_raw: list[Any] = tags_obj if isinstance(tags_obj, list) else []
    tags = [_normalize_tag(item) for item in tags_raw if _normalize_tag(item)][:_PROFILE_DIGEST_TAG_MAX]

    summary = _clean_single_line(
        user_vector.get("summary")
        or profile.get("summary")
        or profile.get("name")
    )[:_PROFILE_SUMMARY_MAX_CHARS]

    confidence = _resolve_profile_confidence(profile, user_vector, provenance)
    profile_version = _resolve_profile_version_pointer(profile, provenance, raw_profile)

    return {
        "architecture_requests": architecture_requests,
        "constraints": constraints,
        "tags": tags,
        "summary": summary,
        "confidence": confidence,
        "profile_version": profile_version,
    }


def _normalize_constraints(raw: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    out: dict[str, str | int | float | bool | None] = {}
    for key, value in raw.items():
        if len(out) >= _PROFILE_DIGEST_CONSTRAINT_MAX:
            break
        normalized_key = _normalize_constraint_key(key)
        normalized_value = _normalize_constraint_value(value)
        if not normalized_key or normalized_value is None:
            continue
        out[normalized_key] = normalized_value
    return out


def _normalize_constraint_key(value: object) -> str:
    token = re.sub(r"\s+", "_", str(value).strip().lower())
    token = "".join(ch for ch in token if ch.isalnum() or ch == "_")
    return token[:40]


def _normalize_constraint_value(value: object) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 3)
    if value is None:
        return None
    text = _clean_single_line(value).lower()
    return text[:80] if text else None


def _normalize_tag(value: object) -> str:
    token = re.sub(r"\s+", "_", str(value).strip().lower())
    token = "".join(ch for ch in token if ch.isalnum() or ch in {"_", "-"})
    return token[:24]


def _clean_single_line(value: object) -> str:
    return " ".join(str(value).strip().split())


def _extract_clarification(data_or_state: object) -> dict[str, Any]:
    source: dict[str, Any] = {}
    if isinstance(data_or_state, dict):
        clarification_obj = data_or_state.get("clarification_status")
        intent_gate_obj = data_or_state.get("intent_gate")
        if isinstance(clarification_obj, dict):
            source = clarification_obj
        elif isinstance(intent_gate_obj, dict):
            source = intent_gate_obj
        else:
            source = data_or_state

    prompt = _clean_single_line(source.get("clarification_prompt", ""))
    try:
        confidence = float(source.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    slots_candidate = source.get("missing_slots")
    missing_slots_raw = slots_candidate if isinstance(slots_candidate, list) else []
    missing_slots: list[str] = []
    for raw_slot in missing_slots_raw:
        slot = _clean_single_line(raw_slot)[:32]
        if not slot:
            continue
        missing_slots.append(slot)
        if len(missing_slots) >= 6:
            break

    requires_clarification = bool(source.get("requires_clarification") is True)
    unresolved = requires_clarification or bool(missing_slots)
    return {
        "requires_clarification": requires_clarification,
        "intent_class": str(source.get("intent_class", "")).strip()[:48],
        "clarification_prompt": prompt[:_MAX_CLARIFICATION_PROMPT_CHARS],
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "missing_slots": missing_slots,
        "updated_at": str(source.get("updated_at", "")).strip()[:48],
        "status": "unresolved" if unresolved else "resolved",
        "unresolved": unresolved,
    }


def _resolve_profile_confidence(
    profile: dict[str, Any],
    user_vector: dict[str, Any],
    provenance: dict[str, Any],
) -> float:
    candidates = [
        profile.get("confidence"),
        user_vector.get("confidence"),
        provenance.get("confidence"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, (int, float, str)):
            continue
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        return round(max(0.0, min(1.0, value)), 2)
    return 0.0


def _resolve_profile_version_pointer(profile: dict[str, Any], provenance: dict[str, Any], raw_profile: str) -> str:
    for candidate in (
        profile.get("profile_version"),
        profile.get("version"),
        provenance.get("checksum"),
        provenance.get("version"),
    ):
        if candidate is None:
            continue
        text = _clean_single_line(candidate)
        if text:
            return text[:64]
    # Deterministic: hash the parsed dict, not the raw text
    return profile_version_from_map(profile)


class ContextEngine:
    """Composes bounded context packets for downstream consumers."""

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)
        self._last_snapshot: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_packet(
        self,
        run_id: str,
        *,
        delta_only: bool = False,
    ) -> dict[str, Any]:
        """Build a compact context packet.

        Returns a dict with keys:
          - ``summary``: bounded text (<=1000 chars)
          - ``artifact_pointers``: list of relative paths to state artifacts
          - ``budget``: ``{max_chars: int, used_chars: int}``
          - ``delta_only``: bool
          - ``run_id``: str
        """
        try:
            return self._build(run_id, delta_only=delta_only)
        except Exception:
            return self._fallback(run_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build(self, run_id: str, *, delta_only: bool) -> dict[str, Any]:
        profile_digest = load_profile_digest(self.project_dir)
        profile_id_raw = str(profile_digest.get("profile_version", "")).strip()
        profile_id = profile_id_raw if profile_id_raw else None

        coordinator_run_id = self._resolve_coordinator_run_id(run_id)
        scoped_run_id = coordinator_run_id or run_id

        raw = self._read_all_state(scoped_run_id)
        clarification_status = self._compose_clarification_status(raw)
        ambiguity_state = self._compose_ambiguity_state(raw)
        provenance_only = bool(ambiguity_state.get("unresolved") is True)

        release_metadata, release_pointers = self._compose_release_metadata(scoped_run_id)
        artifact_pointers = self._collect_artifact_pointers(scoped_run_id)
        provenance_pointers = self._merge_provenance_pointers(artifact_pointers, release_pointers)
        artifact_handles = self._collect_artifact_handles(scoped_run_id, profile_id=profile_id)

        if (
            not provenance_pointers
            and not artifact_handles
            and all(v == {} for v in raw.values())
            and not release_metadata
        ):
            pkt = self._fallback(run_id, coordinator_run_id=coordinator_run_id)
            pkt["delta_only"] = delta_only
            pkt["profile_digest"] = profile_digest
            self._persist_packet(pkt)
            self._index_governed_packet(pkt, scoped_run_id=scoped_run_id, profile_id=profile_id)
            return pkt

        summary = (
            self._provenance_only_summary(clarification_status)
            if provenance_only
            else self._compose_summary(raw)
        )
        current_snapshot = self._snapshot_key(
            {
                **raw,
                "_release_metadata": release_metadata,
                "_ambiguity_state": ambiguity_state,
                "_provenance_only": provenance_only,
            }
        )

        if delta_only and self._last_snapshot is not None and not provenance_only:
            changed_keys: list[str] = []
            for key in current_snapshot:
                if current_snapshot.get(key) != self._last_snapshot.get(key):
                    changed_keys.append(key)

            if not changed_keys:
                summary = "no changes since last packet"
                artifact_pointers = []
                provenance_pointers = []

        self._last_snapshot = current_snapshot

        packet: dict[str, Any] = {
            "packet_version": _PACKET_VERSION,
            "summary": summary,
            "artifact_pointers": artifact_pointers,
            "provenance_pointers": provenance_pointers,
            "artifact_handles": artifact_handles,
            "clarification_status": clarification_status,
            "ambiguity_state": ambiguity_state,
            "provenance_only": provenance_only,
            "governance": self._compose_governance(raw),
            "release_metadata": release_metadata,
            "coordinator_run_id": coordinator_run_id,
            "profile_digest": profile_digest,
            "budget": {
                "max_chars": _MAX_SUMMARY_CHARS,
                "used_chars": len(summary),
            },
            "delta_only": delta_only,
            "run_id": run_id,
            "deterministic_contract": build_deterministic_contract(run_id),
        }
        if not provenance_only:
            packet["derived_action_summary"] = summary

        self._persist_packet(packet)
        self._index_governed_packet(packet, scoped_run_id=scoped_run_id, profile_id=profile_id)
        return packet

    def _read_all_state(self, run_id: str) -> dict[str, Any]:
        """Read all state files, returning empty dicts for missing ones."""
        result: dict[str, Any] = {}
        for name, rel_path in _STATE_PATHS.items():
            result[name] = self._read_json(self.project_dir / rel_path)
        result["council_verdicts"] = self._read_json(self.project_dir / _COUNCIL_REL_BASE / f"{run_id}.json")
        result["intent_gate"] = self._read_json(self.project_dir / _INTENT_GATE_REL_BASE / f"{run_id}.json")
        return result

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _collect_artifact_pointers(self, run_id: str) -> list[str]:
        """Collect relative paths to existing state artifacts — NO raw content."""
        pointers: list[str] = []
        for rel_path in _STATE_PATHS.values():
            full = self.project_dir / rel_path
            if full.exists():
                pointers.append(str(rel_path))

        council_rel = _COUNCIL_REL_BASE / f"{run_id}.json"
        if (self.project_dir / council_rel).exists():
            pointers.append(str(council_rel))

        intent_gate_rel = _INTENT_GATE_REL_BASE / f"{run_id}.json"
        if (self.project_dir / intent_gate_rel).exists():
            pointers.append(str(intent_gate_rel))
        return pointers

    def _resolve_coordinator_run_id(self, run_id: str) -> str:
        try:
            module = __import__("runtime.release_run_coordinator", fromlist=["get_active_coordinator_run_id"])
            resolver = getattr(module, "get_active_coordinator_run_id", None)
            if callable(resolver):
                active_run_id = resolver(str(self.project_dir))
                if isinstance(active_run_id, str) and active_run_id.strip():
                    return active_run_id.strip()
        except Exception:
            pass
        return run_id

    def _compose_release_metadata(self, run_id: str) -> tuple[dict[str, Any], list[str]]:
        run_token = str(run_id).strip()
        if not run_token:
            return {}, []

        state_rel = _RELEASE_COORDINATOR_REL_BASE / f"{run_token}.json"
        evidence_rel = _RELEASE_COORDINATOR_REL_BASE / f"{run_token}-release-evidence.json"
        council_rel = _RELEASE_COORDINATOR_REL_BASE / run_token / "council.json"
        rollback_rel = _RELEASE_COORDINATOR_REL_BASE / run_token / "rollback.json"

        pointers: list[str] = []
        for rel_path in (state_rel, evidence_rel, council_rel, rollback_rel):
            if (self.project_dir / rel_path).exists():
                pointers.append(str(rel_path))

        state_payload = self._read_json(self.project_dir / state_rel)
        evidence_payload = self._read_json(self.project_dir / evidence_rel)
        if not state_payload and not evidence_payload and not pointers:
            return {}, []

        evidence_links_obj = state_payload.get("evidence_links")
        evidence_links = evidence_links_obj if isinstance(evidence_links_obj, list) else []
        claims_obj = evidence_payload.get("claims")
        claims = claims_obj if isinstance(claims_obj, list) else []
        artifact_obj = evidence_payload.get("artifact")
        artifact = artifact_obj if isinstance(artifact_obj, dict) else {}
        attestation_obj = artifact.get("attestation")

        metadata = {
            "run_id": str(state_payload.get("run_id", run_token)).strip(),
            "status": str(state_payload.get("status", "")).strip()[:24],
            "phase": str(state_payload.get("phase", "")).strip()[:24],
            "resolution_source": str(state_payload.get("resolution_source", "")).strip()[:24],
            "resolution_reason": str(state_payload.get("resolution_reason", "")).strip()[:80],
            "health_action": str(state_payload.get("health_action", "")).strip()[:48],
            "compliance_authority": str(state_payload.get("compliance_authority", "")).strip()[:48],
            "compliance_reason": str(state_payload.get("compliance_reason", "")).strip()[:120],
            "evidence_links_count": len(evidence_links),
            "claim_count": len(claims),
            "has_release_evidence": bool(evidence_payload),
            "artifact_attested": isinstance(attestation_obj, dict),
        }
        return metadata, pointers

    def _merge_provenance_pointers(self, pointers: list[str], release_pointers: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for raw_pointer in [*pointers, *release_pointers]:
            pointer = str(raw_pointer).strip()
            if not pointer or pointer in seen:
                continue
            seen.add(pointer)
            merged.append(pointer)
            if len(merged) >= _MAX_PROVENANCE_POINTERS:
                break
        return merged

    def _compose_ambiguity_state(self, raw: dict[str, Any]) -> dict[str, Any]:
        clarification = _extract_clarification(raw)
        return {
            "status": str(clarification.get("status", "resolved")),
            "unresolved": bool(clarification.get("unresolved") is True),
            "requires_clarification": bool(clarification.get("requires_clarification") is True),
            "missing_slots": list(clarification.get("missing_slots", [])),
            "updated_at": str(clarification.get("updated_at", "")).strip()[:48],
        }

    def _provenance_only_summary(self, clarification_status: dict[str, Any]) -> str:
        intent_class = str(clarification_status.get("intent_class", "")).strip()
        if intent_class:
            return f"clarification pending for intent={intent_class}; provenance-only packet"[:_MAX_SUMMARY_CHARS]
        return "clarification pending; provenance-only packet"

    def _index_governed_packet(self, packet: dict[str, Any], *, scoped_run_id: str, profile_id: str | None) -> None:
        run_token = str(scoped_run_id).strip()
        if not run_token:
            return

        clarification_obj = packet.get("clarification_status")
        clarification = clarification_obj if isinstance(clarification_obj, dict) else {}
        release_obj = packet.get("release_metadata")
        release_metadata = release_obj if isinstance(release_obj, dict) else {}

        metadata: dict[str, Any] = {
            "packet_version": str(packet.get("packet_version", "")).strip(),
            "coordinator_run_id": str(packet.get("coordinator_run_id", "")).strip(),
            "provenance_only": bool(packet.get("provenance_only") is True),
            "artifact_pointer_count": len(packet.get("artifact_pointers", [])) if isinstance(packet.get("artifact_pointers"), list) else 0,
            "provenance_pointer_count": len(packet.get("provenance_pointers", [])) if isinstance(packet.get("provenance_pointers"), list) else 0,
            "artifact_handle_count": len(packet.get("artifact_handles", [])) if isinstance(packet.get("artifact_handles"), list) else 0,
            "requires_clarification": bool(clarification.get("requires_clarification") is True),
            "intent_class": str(clarification.get("intent_class", "")).strip()[:48],
            "release_phase": str(release_metadata.get("phase", "")).strip()[:24],
            "release_status": str(release_metadata.get("status", "")).strip()[:24],
        }

        try:
            store = MemoryStore(store_path=str(self.project_dir / _MEMORY_STORE_REL_PATH))
            scoped_profile_id = str(profile_id or "")
            existing = store.query_artifacts(
                run_id=run_token,
                profile_id=scoped_profile_id or None,
                kind=_CONTEXT_PACKET_KIND,
                limit=1,
            )
            if existing:
                store.close()
                return
            store.index_artifact(
                run_id=run_token,
                profile_id=scoped_profile_id,
                kind=_CONTEXT_PACKET_KIND,
                path=str(_PACKET_REL_PATH),
                summary=_CONTEXT_PACKET_SUMMARY,
                metadata=metadata,
            )
            store.close()
        except Exception:
            pass

    def _compose_clarification_status(self, raw: dict[str, Any]) -> dict[str, Any]:
        clarification = _extract_clarification(raw)
        return {
            "requires_clarification": bool(clarification.get("requires_clarification") is True),
            "intent_class": str(clarification.get("intent_class", "")).strip()[:48],
            "clarification_prompt": str(clarification.get("clarification_prompt", "")).strip()[:_MAX_CLARIFICATION_PROMPT_CHARS],
            "confidence": round(float(clarification.get("confidence", 0.0)), 2),
        }

    def _compose_governance(self, raw: dict[str, Any]) -> dict[str, Any]:
        intent_gate = raw.get("intent_gate", {})
        if not isinstance(intent_gate, dict):
            return {}
        governance = intent_gate.get("governance")
        if isinstance(governance, dict):
            return dict(governance)
        return {}

    def _compose_summary(self, raw: dict[str, Any]) -> str:
        """Compose a bounded summary from state signals."""
        parts: list[str] = []

        # Architecture signal
        arch = raw.get("architecture_signal", {})
        arch_summary = arch.get("summary", "")
        if arch_summary and arch_summary != "no architecture signals available":
            parts.append(f"arch: {arch_summary[:500]}")

        # Defense state
        defense = raw.get("defense_state", {})
        risk = defense.get("risk_level", "")
        actions = defense.get("actions", [])
        if risk:
            action_str = ", ".join(actions) if actions else "none"
            parts.append(f"defense: risk={risk} actions=[{action_str}]")

        # Background verification
        verif = raw.get("background_verification", {})
        v_status = verif.get("status", "")
        blockers = verif.get("blockers", [])
        if v_status:
            blocker_str = f" blockers={len(blockers)}" if blockers else ""
            parts.append(f"verification: status={v_status}{blocker_str}")

        # Context pressure
        pressure = raw.get("context_pressure", {})
        tool_count = pressure.get("tool_count")
        is_high = pressure.get("is_high")
        if tool_count is not None:
            parts.append(f"pressure: tools={tool_count} high={is_high}")

        council = raw.get("council_verdicts", {})
        if isinstance(council, dict):
            verdicts = council.get("verdicts")
            if isinstance(verdicts, dict) and verdicts:
                evidence = verdicts.get("evidence_completeness")
                if isinstance(evidence, dict):
                    token = str(evidence.get("verdict", "")).strip().lower() or "unknown"
                    parts.append(f"council: evidence_completeness={token}")

        if not parts:
            return "no context signals available"

        summary = " | ".join(parts)
        return summary[:_MAX_SUMMARY_CHARS]

    def _snapshot_key(self, raw: dict[str, Any]) -> dict[str, str]:
        """Create a hashable snapshot of raw state for delta comparison."""
        snap: dict[str, str] = {}
        for key, value in raw.items():
            snap[key] = json.dumps(value, sort_keys=True, ensure_ascii=True)
        return snap

    def _persist_packet(self, packet: dict[str, Any]) -> None:
        """Write packet to .omg/state/context_engine_packet.json atomically."""
        path = self.project_dir / _PACKET_REL_PATH
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.tmp")
            tmp.write_text(
                json.dumps(packet, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            os.rename(tmp, path)
        except Exception:
            pass  # crash isolation

    def _fallback(self, run_id: str, *, coordinator_run_id: str = "") -> dict[str, Any]:
        return {
            "packet_version": _PACKET_VERSION,
            "summary": "no context signals available",
            "artifact_pointers": [],
            "provenance_pointers": [],
            "artifact_handles": [],
            "clarification_status": {
                "requires_clarification": False,
                "intent_class": "",
                "clarification_prompt": "",
                "confidence": 0.0,
            },
            "ambiguity_state": {
                "status": "resolved",
                "unresolved": False,
                "requires_clarification": False,
                "missing_slots": [],
                "updated_at": "",
            },
            "provenance_only": False,
            "governance": {},
            "release_metadata": {},
            "coordinator_run_id": coordinator_run_id,
            "profile_digest": _empty_profile_digest(),
            "budget": {"max_chars": _MAX_SUMMARY_CHARS, "used_chars": 0},
            "delta_only": False,
            "run_id": run_id,
            "deterministic_contract": build_deterministic_contract(run_id),
        }

    def _collect_artifact_handles(self, run_id: str, *, profile_id: str | None = None) -> list[dict[str, Any]]:
        run_token = str(run_id).strip()
        if not run_token:
            return []
        try:
            profile_id_raw = str(profile_id or "").strip()
            if not profile_id_raw:
                digest_profile_id = str(load_profile_digest(self.project_dir).get("profile_version", "")).strip()
                profile_id_raw = digest_profile_id
            scoped_profile_id = profile_id_raw if profile_id_raw else None
            store = MemoryStore(store_path=str(self.project_dir / _MEMORY_STORE_REL_PATH))
            handles = store.query_artifacts(run_id=run_token, profile_id=scoped_profile_id)
            store.close()
            return handles
        except Exception:
            return []


# ---------------------------------------------------------------------------
# NF3c: Folder-scoped context files
# ---------------------------------------------------------------------------

_CONTEXT_CACHE_REL_BASE = Path(".omg") / "context"


def _folder_hash(folder_path: str) -> str:
    """Generate a deterministic hash for a folder path."""
    import hashlib

    normalized = folder_path.strip().rstrip("/\\")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def get_folder_context(project_dir: str, folder_path: str) -> str | None:
    """Read cached folder context from .omg/context/<folder-hash>.md.

    Returns the cached content if:
      - The cache file exists
      - The folder mtime <= context file mtime (cache is fresh)

    Returns None if cache is stale or missing (caller should regenerate).
    """
    root = Path(project_dir)
    folder = Path(folder_path)

    # Compute hash and locate cache file
    folder_hash = _folder_hash(folder_path)
    cache_path = root / _CONTEXT_CACHE_REL_BASE / f"{folder_hash}.md"

    if not cache_path.exists():
        return None

    # Check freshness: folder mtime vs cache mtime
    try:
        if folder.exists():
            folder_mtime = folder.stat().st_mtime
            cache_mtime = cache_path.stat().st_mtime
            if folder_mtime > cache_mtime:
                # Folder was modified after cache — cache is stale
                return None
    except OSError:
        # If we can't stat, treat as stale
        return None

    # Read cached content
    try:
        return cache_path.read_text(encoding="utf-8")
    except OSError:
        return None


def save_folder_context(project_dir: str, folder_path: str, content: str) -> str:
    """Write folder context to .omg/context/<folder-hash>.md.

    Args:
        project_dir: Root project directory.
        folder_path: The folder this context describes.
        content: Markdown content to cache.

    Returns:
        The path to the created cache file.
    """
    root = Path(project_dir)
    folder_hash = _folder_hash(folder_path)
    cache_path = root / _CONTEXT_CACHE_REL_BASE / f"{folder_hash}.md"

    # Write atomically
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_name(f"{cache_path.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.rename(tmp, cache_path)

    return str(cache_path)


# ---------------------------------------------------------------------------
# NF3d: Context entry scoring (read-only-what-you-need heuristics)
# ---------------------------------------------------------------------------

import math
import time


def score_context_entry(entry: dict, active_task: str | None = None) -> float:
    """Score a context entry from 0.0 to 1.0.

    Scoring factors:
      - Recency: newer entries score higher (exponential decay over 1 hour)
      - Relevance: entries mentioning active task keywords score higher
      - Type: plan/checklist entries get a base boost of +0.3
      - Usage: entries that were read/referenced get a boost

    Args:
        entry: A dict with keys like 'timestamp', 'type', 'content', 'referenced'.
        active_task: The current task description (for keyword matching).

    Returns:
        A float score between 0.0 and 1.0.
    """
    score = 0.0

    # Recency component (max 0.4)
    timestamp = entry.get("timestamp") or entry.get("created_at") or entry.get("updated_at")
    if timestamp:
        try:
            if isinstance(timestamp, (int, float)):
                entry_time = float(timestamp)
            else:
                # Parse ISO format
                from datetime import datetime as dt

                ts_str = str(timestamp).replace("Z", "+00:00")
                parsed = dt.fromisoformat(ts_str)
                entry_time = parsed.timestamp()

            now = time.time()
            age_seconds = max(0, now - entry_time)
            # Exponential decay: half-life of 1 hour (3600 seconds)
            decay = math.exp(-age_seconds / 3600)
            score += 0.4 * decay
        except (TypeError, ValueError, OSError):
            # If we can't parse timestamp, give minimal recency score
            score += 0.1

    # Type boost (max +0.3)
    entry_type = str(entry.get("type", "")).lower()
    if entry_type in {"plan", "checklist", "_plan", "_checklist"}:
        score += 0.3
    elif entry_type in {"task", "focus", "task_focus"}:
        score += 0.2
    elif entry_type in {"unsolved", "blocker", "error"}:
        score += 0.25

    # Usage/reference boost (max +0.1)
    if entry.get("referenced") or entry.get("read_count", 0) > 0:
        score += 0.1

    # Relevance to active task (max +0.2)
    if active_task:
        content = str(entry.get("content", "")).lower()
        summary = str(entry.get("summary", "")).lower()
        combined = f"{content} {summary}"

        # Extract meaningful words from active task
        task_words = set(
            word for word in re.findall(r"\b[a-z0-9]{3,}\b", active_task.lower())
            if word not in {"the", "and", "for", "with", "this", "that", "from", "into"}
        )

        if task_words:
            matches = sum(1 for word in task_words if word in combined)
            relevance_ratio = matches / len(task_words)
            score += 0.2 * relevance_ratio

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def rank_context_entries(entries: list[dict], active_task: str | None = None) -> list[dict]:
    """Score each entry and sort by score descending.

    Args:
        entries: List of context entry dicts.
        active_task: The current task description (for relevance scoring).

    Returns:
        Sorted list with '_score' field added to each entry.
    """
    scored: list[dict] = []
    for entry in entries:
        entry_copy = dict(entry)
        entry_copy["_score"] = score_context_entry(entry, active_task)
        scored.append(entry_copy)

    # Sort by score descending
    scored.sort(key=lambda e: e.get("_score", 0.0), reverse=True)
    return scored


# ---------------------------------------------------------------------------
# NF3e: Smart compact
# ---------------------------------------------------------------------------


def _is_protected_entry(entry: dict) -> bool:
    """Check if an entry should never be dropped during compaction.

    Protected types:
      - plan, checklist (active planning state)
      - task_focus (active task)
      - unsolved, blocker, error (critical issues)
    """
    entry_type = str(entry.get("type", "")).lower()
    protected_types = {"plan", "checklist", "_plan", "_checklist", "task_focus", "unsolved", "blocker", "error"}

    if entry_type in protected_types:
        return True

    # Also protect entries explicitly marked as protected
    if entry.get("protected"):
        return True

    return False


def smart_compact(
    project_dir: str,
    entries: list[dict],
    drop_ratio: float = 0.4,
) -> dict:
    """Compact context entries by dropping lowest-scoring non-protected entries.

    Protected entries (never dropped):
      - plan, checklist, task_focus
      - unsolved, blocker, error
      - Entries with 'protected': True

    Args:
        project_dir: Root project directory (for potential state lookups).
        entries: List of context entry dicts.
        drop_ratio: Fraction of entries to drop (0.0 to 1.0). Default 0.4 (40%).

    Returns:
        {
            "kept": list of kept entries,
            "dropped": list of dropped entries,
            "kept_count": int,
            "dropped_count": int,
        }
    """
    if not entries:
        return {"kept": [], "dropped": [], "kept_count": 0, "dropped_count": 0}

    # Get active task for relevance scoring
    active_task_data = get_active_task(project_dir)
    active_task_str = active_task_data.get("task") if active_task_data else None

    # Score all entries
    scored_entries = rank_context_entries(entries, active_task_str)

    # Separate protected vs droppable
    protected: list[dict] = []
    droppable: list[dict] = []

    for entry in scored_entries:
        if _is_protected_entry(entry):
            protected.append(entry)
        else:
            droppable.append(entry)

    # Calculate how many to drop from droppable entries
    target_drop_count = int(len(droppable) * drop_ratio)

    # Drop from the lowest-scoring entries (they're already sorted by score descending)
    # So we keep the first (len - target_drop_count) and drop the rest
    keep_count = len(droppable) - target_drop_count
    kept_droppable = droppable[:keep_count]
    dropped = droppable[keep_count:]

    # Combine protected + kept droppable
    kept = protected + kept_droppable

    return {
        "kept": kept,
        "dropped": dropped,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
    }
