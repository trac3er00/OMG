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

_STATE_PATHS = {
    "architecture_signal": Path(".omg") / "state" / "architecture_signal" / "latest.json",
    "defense_state": Path(".omg") / "state" / "defense_state" / "current.json",
    "background_verification": Path(".omg") / "state" / "background-verification.json",
    "context_pressure": Path(".omg") / "state" / ".context-pressure.json",
}
_COUNCIL_REL_BASE = Path(".omg") / "state" / "council_verdicts"
_INTENT_GATE_REL_BASE = Path(".omg") / "state" / "intent_gate"


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
        raw = self._read_all_state(run_id)
        artifact_pointers = self._collect_artifact_pointers(run_id)
        artifact_handles = self._collect_artifact_handles(run_id)

        if not artifact_pointers and not artifact_handles and all(v == {} for v in raw.values()):
            pkt = self._fallback(run_id)
            pkt["delta_only"] = delta_only
            pkt["profile_digest"] = load_profile_digest(self.project_dir)
            self._persist_packet(pkt)
            return pkt

        summary = self._compose_summary(raw)
        current_snapshot = self._snapshot_key(raw)

        if delta_only and self._last_snapshot is not None:
            changed_keys: list[str] = []
            for key in current_snapshot:
                if current_snapshot.get(key) != self._last_snapshot.get(key):
                    changed_keys.append(key)

            if not changed_keys:
                summary = "no changes since last packet"
                artifact_pointers = []

        self._last_snapshot = current_snapshot

        packet: dict[str, Any] = {
            "summary": summary,
            "artifact_pointers": artifact_pointers,
            "artifact_handles": artifact_handles,
            "clarification_status": self._compose_clarification_status(raw),
            "governance": self._compose_governance(raw),
            "profile_digest": load_profile_digest(self.project_dir),
            "budget": {
                "max_chars": _MAX_SUMMARY_CHARS,
                "used_chars": len(summary),
            },
            "delta_only": delta_only,
            "run_id": run_id,
            "deterministic_contract": build_deterministic_contract(run_id),
        }

        self._persist_packet(packet)
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

    def _compose_clarification_status(self, raw: dict[str, Any]) -> dict[str, Any]:
        intent_gate = raw.get("intent_gate", {})
        if not isinstance(intent_gate, dict):
            intent_gate = {}

        prompt = str(intent_gate.get("clarification_prompt", "")).strip().replace("\n", " ")
        confidence_raw = intent_gate.get("confidence", 0.0)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return {
            "requires_clarification": bool(intent_gate.get("requires_clarification") is True),
            "intent_class": str(intent_gate.get("intent_class", "")).strip()[:48],
            "clarification_prompt": prompt[:_MAX_CLARIFICATION_PROMPT_CHARS],
            "confidence": round(confidence, 2),
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

    def _fallback(self, run_id: str) -> dict[str, Any]:
        return {
            "summary": "no context signals available",
            "artifact_pointers": [],
            "artifact_handles": [],
            "clarification_status": {
                "requires_clarification": False,
                "intent_class": "",
                "clarification_prompt": "",
                "confidence": 0.0,
            },
            "governance": {},
            "profile_digest": _empty_profile_digest(),
            "budget": {"max_chars": _MAX_SUMMARY_CHARS, "used_chars": 0},
            "delta_only": False,
            "run_id": run_id,
            "deterministic_contract": build_deterministic_contract(run_id),
        }

    def _collect_artifact_handles(self, run_id: str) -> list[dict[str, Any]]:
        try:
            profile_id_raw = str(load_profile_digest(self.project_dir).get("profile_version", "")).strip()
            profile_id = profile_id_raw if profile_id_raw else None
            store = MemoryStore(store_path=str(self.project_dir / _MEMORY_STORE_REL_PATH))
            return store.query_artifacts(run_id=run_id, profile_id=profile_id)
        except Exception:
            return []
