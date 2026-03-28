"""Context profile and packet management for OMG runtime orchestration.

This module derives profile digests from project state, composes bounded
run-scoped context packets, tracks provenance/artifact pointers, and exposes
session context helpers (scoring, compaction, task focus, and handoff
snapshots). The packet builder is crash-isolated and returns fallback packets on
errors instead of propagating exceptions.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from runtime.forge_run_id import build_deterministic_contract
from runtime.memory_store import MemoryStore
from runtime.profile_io import profile_version_from_map

_logger = logging.getLogger(__name__)

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


def load_profile_digest(project_dir: str | Path) -> dict[str, Any]:
    """Load and normalize the profile digest used by runtime components.

    Args:
        project_dir: Project root containing ``.omg/state/profile.yaml``.

    Returns:
        Normalized digest with architecture requests, constraints, tags,
        summary, confidence, and profile version pointer.
    """
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
    except Exception as exc:
        _logger.debug("Failed to parse profile YAML from %s: %s", profile_path, exc, exc_info=True)
        payload = None
    if isinstance(payload, dict):
        parsed = payload

    digest = _profile_digest_from_map(parsed, raw_profile)
    return digest


def render_profile_digest_text(project_dir: str | Path, *, max_chars: int) -> str:
    """Render a bounded single-line textual summary for profile digest context.

    Args:
        project_dir: Project root used to load profile digest data.
        max_chars: Maximum number of characters in the rendered summary.

    Returns:
        Compact digest string truncated to ``max_chars``.
    """
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
    """Compose run-scoped context packets with provenance-safe summaries."""

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
        """Build a bounded context packet for a run.

        Args:
            run_id: Run identifier for packet scoping.
            delta_only: Whether to emit only changed summary context since the
                previous packet snapshot.

        Returns:
            Context packet containing summary text, provenance/artifact pointers,
            clarification/governance metadata, budget usage, and deterministic
            contract metadata.
        """
        try:
            return self._build(run_id, delta_only=delta_only)
        except Exception as exc:
            _logger.debug("Failed to build context packet for run %s: %s", run_id, exc, exc_info=True)
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
        except Exception as exc:
            _logger.debug("Failed to resolve coordinator run id for %s: %s", run_id, exc, exc_info=True)
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
        except Exception as exc:
            _logger.debug("Failed to index context packet for run %s: %s", run_token, exc, exc_info=True)

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
        except Exception as exc:
            _logger.debug("Failed to persist context packet to %s: %s", path, exc, exc_info=True)

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
        except Exception as exc:
            _logger.debug("Failed to load artifact handles for run %s: %s", run_token, exc, exc_info=True)
            return []


# ── NF3c: Folder-scoped context cache ────────────────────────────────────────

_CONTEXT_CACHE_DIR = Path(".omg") / "context"


def _folder_cache_path(project_dir: str | Path, folder_path: str) -> Path:
    """Return the cache file path for a given folder."""
    import hashlib
    folder_hash = hashlib.sha256(folder_path.encode()).hexdigest()[:16]
    return Path(project_dir) / _CONTEXT_CACHE_DIR / f"{folder_hash}.md"


def get_folder_context(project_dir: str | Path, folder_path: str) -> str | None:
    """Return cached folder context when cache exists and is still fresh.

    Args:
        project_dir: Project root used for cache location.
        folder_path: Folder whose cache should be resolved.

    Returns:
        Cached Markdown context, or ``None`` when missing/stale/unreadable.
    """
    cache_path = _folder_cache_path(project_dir, folder_path)
    if not cache_path.exists():
        return None

    # Check if folder exists and compare modification times
    folder = Path(folder_path)
    if not folder.exists():
        return None

    try:
        cache_mtime = cache_path.stat().st_mtime
        # Recursively find the latest mtime among all files inside the folder
        # (folder mtime alone doesn't update when files inside are edited)
        latest_mtime = max(
            (p.stat().st_mtime for p in folder.rglob("*")),
            default=folder.stat().st_mtime,
        )
        if latest_mtime > cache_mtime:
            return None  # Cache is stale
        return cache_path.read_text(encoding="utf-8")
    except OSError:
        return None


def save_folder_context(project_dir: str | Path, folder_path: str, content: str) -> str:
    """Persist folder context content to the folder-scoped cache.

    Args:
        project_dir: Project root used for cache location.
        folder_path: Folder identifier used to derive cache key.
        content: Markdown context to cache.

    Returns:
        Absolute/relative path to the written cache file.
    """
    cache_path = _folder_cache_path(project_dir, folder_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(content, encoding="utf-8")
    return str(cache_path)


# ── NF3d: Context entry scoring ──────────────────────────────────────────────

import time as _time


def score_context_entry(entry: dict[str, Any], active_task: str | None = None) -> float:
    """Score a context entry for relevance and priority.

    Scoring factors:
    - Recency: entries decay over time (half-life ~1 hour)
    - Type boost: plan/checklist entries get +0.3
    - Task relevance: keyword overlap with active_task gives boost
    - Usage boost: referenced entries score higher

    Args:
        entry: Context entry payload to score.
        active_task: Optional active task string for keyword relevance.

    Returns:
        Relevance score in the ``[0.0, 1.0]`` range.
    """
    score = 0.3  # Base score (lower to prevent clamping)

    # Recency decay (half-life ~1 hour = 3600 seconds)
    now = _time.time()
    timestamp = entry.get("timestamp", now)
    age_seconds = max(0, now - timestamp)
    recency_factor = 0.5 ** (age_seconds / 3600)  # Half-life decay
    score += 0.2 * recency_factor  # Max +0.2 for very recent entries

    # Type boost
    entry_type = entry.get("type", "general")
    type_boosts = {
        "plan": 0.3,
        "checklist": 0.3,
        "task_focus": 0.25,
        "unsolved": 0.2,
        "blocker": 0.2,
        "error": 0.15,
    }
    score += type_boosts.get(entry_type, 0.0)

    # Task relevance boost (keyword overlap)
    if active_task:
        content = entry.get("content", "")
        task_keywords = set(active_task.lower().split())
        content_keywords = set(content.lower().split())
        overlap = len(task_keywords & content_keywords)
        if overlap > 0:
            score += min(0.15, overlap * 0.05)  # Max +0.15 for relevance

    # Usage/reference boost
    if entry.get("referenced"):
        score += 0.1

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def rank_context_entries(
    entries: list[dict[str, Any]],
    active_task: str | None = None,
) -> list[dict[str, Any]]:
    """Rank context entries by descending relevance score.

    Args:
        entries: Context entries to score and rank.
        active_task: Optional active task string for relevance weighting.

    Returns:
        Ranked entries, each augmented with a ``_score`` field.
    """
    scored_entries = []
    for entry in entries:
        entry_copy = dict(entry)
        entry_copy["_score"] = score_context_entry(entry, active_task)
        scored_entries.append(entry_copy)

    scored_entries.sort(key=lambda e: e["_score"], reverse=True)
    return scored_entries


# ── NF3e: Smart compact ──────────────────────────────────────────────────────

_PROTECTED_TYPES = frozenset({"plan", "checklist", "task_focus", "unsolved", "blocker", "error"})


def smart_compact(
    project_dir: str | Path,
    entries: list[dict[str, Any]],
    drop_ratio: float = 0.3,
    active_task: str | None = None,
) -> dict[str, Any]:
    """Intelligently compact context entries by dropping lowest-scoring ones.

    Protected entries (plan, checklist, task_focus, unsolved, blocker, error)
    and entries with 'protected': True are never dropped.

    Args:
        project_dir: Project root directory (for potential persistence)
        entries: List of context entries
        drop_ratio: Fraction of droppable entries to drop (0.0-1.0)
        active_task: Optional active task for relevance scoring

    Returns:
        Dict with 'kept', 'dropped', 'kept_count', 'dropped_count' keys.
    """
    if not entries:
        return {"kept": [], "dropped": [], "kept_count": 0, "dropped_count": 0}

    # Score all entries first
    scored = rank_context_entries(entries, active_task)

    # Separate protected and droppable
    protected: list[dict[str, Any]] = []
    droppable: list[dict[str, Any]] = []

    for entry in scored:
        entry_type = entry.get("type", "general")
        is_protected = (
            entry_type in _PROTECTED_TYPES
            or entry.get("protected") is True
        )
        if is_protected:
            protected.append(entry)
        else:
            droppable.append(entry)

    # Sort droppable by score ascending (lowest first = drop candidates)
    droppable.sort(key=lambda e: e["_score"])

    # Calculate how many to drop
    drop_count = int(len(droppable) * drop_ratio)

    dropped = droppable[:drop_count]
    kept_droppable = droppable[drop_count:]

    # Combine protected + kept droppable
    kept = protected + kept_droppable

    return {
        "kept": kept,
        "dropped": dropped,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
    }


# ---------------------------------------------------------------------------
# NF3a: One-task-per-session (task focus management)
# ---------------------------------------------------------------------------

_SESSION_REL_PATH = Path(".omg") / "state" / "session.json"
_SNAPSHOTS_REL_PATH = Path(".omg") / "state" / "snapshots"


def get_active_task(project_dir: str) -> dict[str, Any] | None:
    """Load active task focus from session state.

    Args:
        project_dir: Project root containing ``.omg/state/session.json``.

    Returns:
        ``task_focus`` payload when present and non-empty, else ``None``.
    """
    project_path = Path(project_dir)
    session_path = project_path / _SESSION_REL_PATH

    if not session_path.exists():
        return None

    try:
        session_data = json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    task_focus = session_data.get("task_focus")
    if not isinstance(task_focus, dict):
        return None

    task = str(task_focus.get("task", "")).strip()
    if not task:
        return None

    return task_focus


def set_task_focus(
    project_dir: str,
    task: str,
    files: list[str] | None = None,
) -> None:
    """Create or update the active task focus in session state.

    Args:
        project_dir: Project root containing ``.omg/state/session.json``.
        task: Task description to persist as current focus.
        files: Optional list of touched files associated with the task.
    """
    from datetime import datetime, timezone

    project_path = Path(project_dir)
    session_path = project_path / _SESSION_REL_PATH

    # Read existing session data if present
    session_data: dict[str, Any] = {}
    if session_path.exists():
        try:
            session_data = json.loads(session_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _logger.debug("Failed to read existing task focus session data from %s: %s", session_path, exc, exc_info=True)

    # Update task_focus
    session_data["task_focus"] = {
        "task": task,
        "files_touched": files or [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write back
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(json.dumps(session_data, indent=2), encoding="utf-8")


def detect_task_drift(
    prompt: str,
    active_task: dict[str, Any] | None,
) -> dict[str, Any]:
    """Detect if a prompt represents task drift from the active task.

    Args:
        prompt: Newly received request text.
        active_task: Active task payload from ``get_active_task``.

    Returns:
        Drift-analysis payload containing drift flag, suggested action,
        normalized active task token, and confidence score.
    """
    if active_task is None:
        return {
            "drift": False,
            "action": "none",
            "suggested_action": "continue",
            "active_task": "",
            "confidence": 1.0,
        }

    task_text = str(active_task.get("task", "")).strip().lower()
    prompt_lower = prompt.lower()

    # Extract keywords from task (filter out common words)
    stop_words = {"the", "a", "an", "to", "for", "of", "in", "on", "at", "is", "and", "or"}
    task_keywords = {
        word for word in task_text.split()
        if len(word) > 2 and word not in stop_words
    }

    # Check keyword overlap
    matching_keywords = sum(1 for kw in task_keywords if kw in prompt_lower)
    overlap_ratio = matching_keywords / len(task_keywords) if task_keywords else 0.0

    # Drift threshold: if less than 30% keyword overlap, consider it drift
    drift_detected = overlap_ratio < 0.3

    return {
        "drift": drift_detected,
        "action": "continue" if not drift_detected else "snapshot",
        "suggested_action": "snapshot" if drift_detected else "continue",
        "active_task": task_text,
        "confidence": 1.0 - overlap_ratio if drift_detected else overlap_ratio,
    }


# ---------------------------------------------------------------------------
# NF3b: Protected handoff snapshot
# ---------------------------------------------------------------------------


def create_handoff_snapshot(project_dir: str) -> str:
    """Create a handoff snapshot of current session state.

    Captures:
    - active_task from session.json
    - plan_state from _plan.md
    - checklist_state from _checklist.md
    - files_touched from task focus

    Args:
        project_dir: Project root where snapshot artifacts are written.

    Returns:
        Path to the created snapshot JSON file.
    """
    from datetime import datetime, timezone

    project_path = Path(project_dir)
    snapshots_dir = project_path / _SNAPSHOTS_REL_PATH
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp-based filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = snapshots_dir / f"{timestamp}.json"

    # Get active task
    active_task = get_active_task(project_dir)

    # Read plan state
    plan_path = project_path / ".omg" / "state" / "_plan.md"
    plan_state: str | None = None
    if plan_path.exists():
        try:
            plan_state = plan_path.read_text(encoding="utf-8")
        except OSError as exc:
            _logger.debug("Failed to read handoff plan state from %s: %s", plan_path, exc, exc_info=True)

    # Read checklist state
    checklist_path = project_path / ".omg" / "state" / "_checklist.md"
    checklist_state: str | None = None
    if checklist_path.exists():
        try:
            checklist_state = checklist_path.read_text(encoding="utf-8")
        except OSError as exc:
            _logger.debug("Failed to read handoff checklist state from %s: %s", checklist_path, exc, exc_info=True)

    # Get files touched
    files_touched: list[str] = []
    if active_task:
        files_touched = active_task.get("files_touched", [])

    snapshot_data = {
        "schema": "HandoffSnapshot",
        "schema_version": "1.0.0",
        "timestamp": timestamp,
        "active_task": active_task,
        "plan_state": plan_state,
        "checklist_state": checklist_state,
        "files_touched": files_touched,
    }

    snapshot_path.write_text(json.dumps(snapshot_data, indent=2), encoding="utf-8")
    return str(snapshot_path)


def list_handoff_snapshots(project_dir: str) -> list[dict[str, Any]]:
    """List handoff snapshots ordered by newest timestamp first.

    Args:
        project_dir: Project root containing snapshot artifacts.

    Returns:
        Snapshot summaries with timestamp, task text, file count, and path.
    """
    project_path = Path(project_dir)
    snapshots_dir = project_path / _SNAPSHOTS_REL_PATH

    if not snapshots_dir.exists():
        return []

    snapshots: list[dict[str, Any]] = []
    for snapshot_file in snapshots_dir.glob("*.json"):
        try:
            data = json.loads(snapshot_file.read_text(encoding="utf-8"))
            active_task = data.get("active_task") or {}
            files_touched = data.get("files_touched", [])
            if not isinstance(files_touched, list):
                files_touched = []

            snapshots.append({
                "timestamp": data.get("timestamp", snapshot_file.stem),
                "task": active_task.get("task", "") if isinstance(active_task, dict) else "",
                "file_count": len(files_touched),
                "path": str(snapshot_file),
            })
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by timestamp descending (newest first)
    snapshots.sort(key=lambda s: s["timestamp"], reverse=True)
    return snapshots
