"""State and provenance tracking for untrusted external content."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from enum import Enum
from typing import Any


STATE_REL_PATH = Path(".omg") / "state" / "untrusted-content.json"
EVIDENCE_REL_DIR = Path(".omg") / "evidence"
_INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"\b(system|assistant|developer)\s*:", re.IGNORECASE),
    re.compile(r"\b(run|execute|commit|push|apply_patch|edit)\b", re.IGNORECASE),
)


class TrustTier(str, Enum):
    LOCAL = "local"
    BALANCED = "balanced"
    RESEARCH = "research"
    BROWSER = "browser"


@dataclass(frozen=True)
class TrustTierConfig:
    tier: TrustTier
    label: str
    score: float
    trusted: bool


TRUST_TIER_CONFIG: dict[TrustTier, TrustTierConfig] = {
    TrustTier.LOCAL: TrustTierConfig(
        tier=TrustTier.LOCAL,
        label="TRUSTED_LOCAL_CONTENT",
        score=1.0,
        trusted=True,
    ),
    TrustTier.BALANCED: TrustTierConfig(
        tier=TrustTier.BALANCED,
        label="TRUSTED_LOCAL_CONTENT",
        score=0.7,
        trusted=True,
    ),
    TrustTier.RESEARCH: TrustTierConfig(
        tier=TrustTier.RESEARCH,
        label="UNTRUSTED_EXTERNAL_CONTENT",
        score=0.0,
        trusted=False,
    ),
    TrustTier.BROWSER: TrustTierConfig(
        tier=TrustTier.BROWSER,
        label="UNTRUSTED_EXTERNAL_CONTENT",
        score=0.0,
        trusted=False,
    ),
}


_SOURCE_TO_TIER: dict[str, TrustTier] = {
    "local": TrustTier.LOCAL,
    "workspace": TrustTier.LOCAL,
    "balanced": TrustTier.BALANCED,
    "tool": TrustTier.BALANCED,
    "web": TrustTier.RESEARCH,
    "research": TrustTier.RESEARCH,
    "mcp": TrustTier.RESEARCH,
    "remote_document": TrustTier.RESEARCH,
    "browser": TrustTier.BROWSER,
    "dom": TrustTier.BROWSER,
    "screenshot": TrustTier.BROWSER,
}


def normalize_trust_tier(tier: TrustTier | str) -> TrustTier:
    if isinstance(tier, TrustTier):
        return tier
    normalized = str(tier).strip().lower()
    if normalized in TrustTier._value2member_map_:
        return TrustTier(normalized)
    raise ValueError(f"Unsupported trust tier: {tier}")


def trust_tier_for_source(source_type: str) -> TrustTier:
    source_key = str(source_type).strip().lower()
    return _SOURCE_TO_TIER.get(source_key, TrustTier.RESEARCH)


def trust_tier_for_preset(preset: str) -> TrustTier:
    mapping = {
        "safe": TrustTier.LOCAL,
        "balanced": TrustTier.BALANCED,
        "interop": TrustTier.RESEARCH,
        "labs": TrustTier.BROWSER,
    }
    return mapping.get(str(preset).strip().lower(), TrustTier.BALANCED)


def tag_content(payload: Any, tier: TrustTier | str) -> dict[str, Any]:
    normalized_tier = normalize_trust_tier(tier)
    config = TRUST_TIER_CONFIG[normalized_tier]
    tagged: dict[str, Any]
    if isinstance(payload, dict):
        tagged = dict(payload)
    else:
        tagged = {"content": payload}
    tagged["_trust_tier"] = normalized_tier.value
    tagged["_trust_label"] = config.label
    tagged["_trust_score"] = config.score
    return tagged


def write_trust_evidence(inputs: list[dict[str, Any]], output_dir: str | Path) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence_path = output_path / f"trust-{timestamp}.json"

    normalized_inputs: list[dict[str, Any]] = []
    for item in inputs:
        data = dict(item)
        trust_tier = str(data.get("_trust_tier", "research"))
        trust_label = str(data.get("_trust_label", "UNTRUSTED_EXTERNAL_CONTENT"))
        try:
            trust_score = float(data.get("_trust_score", 0.0))
        except (TypeError, ValueError):
            trust_score = 0.0
        content_repr = data.get("sanitized_content", data.get("content", ""))
        if not isinstance(content_repr, str):
            content_repr = json.dumps(content_repr, sort_keys=True, ensure_ascii=True)
        content_hash = sha256(content_repr.encode("utf-8")).hexdigest()
        normalized_inputs.append(
            {
                "source_type": str(data.get("source_type", "unknown")),
                "source_ref": str(data.get("source_ref", "")),
                "trust_tier": trust_tier,
                "trust_label": trust_label,
                "trust_score": trust_score,
                "content_hash": content_hash,
            }
        )

    payload = {
        "schema": "TrustEvidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_count": len(normalized_inputs),
        "inputs": normalized_inputs,
    }
    evidence_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return evidence_path.as_posix()


def mark_untrusted_content(
    project_dir: str,
    *,
    source_type: str,
    content: str,
    source_ref: str = "",
    tier: TrustTier | str | None = None,
) -> dict[str, Any]:
    state_path = _state_path(project_dir)
    state = get_untrusted_content_state(project_dir)
    sanitized, quarantined = quarantine_instruction_like_text(content)
    resolved_tier = normalize_trust_tier(tier) if tier is not None else trust_tier_for_source(source_type)
    entry = tag_content(
        {
        "source_type": source_type,
        "source_ref": source_ref,
        "quarantined_fragments": quarantined,
        "sanitized_content": sanitized,
        },
        resolved_tier,
    )
    entry["trust_score"] = entry.get("_trust_score", 0.0)
    provenance = list(state.get("provenance", []))
    provenance.append(entry)
    evidence_path = write_trust_evidence(
        [entry],
        output_dir=Path(project_dir) / EVIDENCE_REL_DIR,
    )

    prior_scores = state.get("trust_scores", {})
    next_external_score = min(
        [
            float(prior_scores.get("external_content", 1.0)),
            float(entry.get("_trust_score", 0.0)),
        ]
    )
    next_state = {
        "active": resolved_tier in {TrustTier.RESEARCH, TrustTier.BROWSER},
        "last_source_type": source_type,
        "last_source_ref": source_ref,
        "last_trust_tier": resolved_tier.value,
        "last_trust_label": entry.get("_trust_label"),
        "last_trust_score": entry.get("_trust_score"),
        "sanitized_content": sanitized,
        "quarantined_fragments": quarantined,
        "provenance": provenance[-20:],
        "trust_scores": {
            **(prior_scores if isinstance(prior_scores, dict) else {}),
            "external_content": next_external_score,
            resolved_tier.value: float(entry.get("_trust_score", 0.0)),
        },
        "evidence_artifacts": (list(state.get("evidence_artifacts", [])) + [evidence_path])[-20:],
    }
    _write_state(state_path, next_state)
    return next_state


def clear_untrusted_content(project_dir: str, *, reason: str) -> dict[str, Any]:
    state_path = _state_path(project_dir)
    existing = get_untrusted_content_state(project_dir)
    next_state = {
        **existing,
        "active": False,
        "cleared_reason": reason,
    }
    _write_state(state_path, next_state)
    return next_state


def get_untrusted_content_state(project_dir: str) -> dict[str, Any]:
    state_path = _state_path(project_dir)
    if not state_path.exists():
        return {
            "active": False,
            "provenance": [],
            "trust_scores": {},
        }
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "active": False,
            "provenance": [],
            "trust_scores": {},
        }
    return payload if isinstance(payload, dict) else {"active": False, "provenance": [], "trust_scores": {}}


def is_untrusted_content_mode_active(project_dir: str) -> bool:
    return bool(get_untrusted_content_state(project_dir).get("active", False))


def quarantine_instruction_like_text(content: str) -> tuple[str, list[str]]:
    sanitized_lines: list[str] = []
    quarantined: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if any(pattern.search(line) for pattern in _INSTRUCTION_PATTERNS):
            quarantined.append(raw_line)
            continue
        sanitized_lines.append(raw_line)
    return "\n".join(sanitized_lines).strip(), quarantined


def _state_path(project_dir: str) -> Path:
    return Path(project_dir) / STATE_REL_PATH


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
