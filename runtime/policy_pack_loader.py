from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict, cast

import yaml

from runtime.canonical_taxonomy import CANONICAL_PRESETS, POLICY_PACK_IDS, RELEASE_CHANNELS, SUBSCRIPTION_TIERS


class PolicyPack(TypedDict):
    id: str
    description: str
    tool_restrictions: list[str]
    network_posture: Literal["open", "restricted", "airgapped"]
    approval_threshold: int
    protected_paths: list[str]
    evidence_requirements: list[str]
    data_sharing: Literal["allowed", "restricted", "prohibited"]


_PACKS_DIR = Path(__file__).resolve().parent.parent / "registry" / "policy-packs"
_REQUIRED_FIELDS = (
    "id",
    "description",
    "tool_restrictions",
    "network_posture",
    "approval_threshold",
    "protected_paths",
    "evidence_requirements",
    "data_sharing",
)
_VALID_NETWORK_POSTURES = {"open", "restricted", "airgapped"}
_VALID_DATA_SHARING = {"allowed", "restricted", "prohibited"}


def list_policy_packs() -> list[str]:
    if not _PACKS_DIR.exists():
        return []
    return sorted(path.stem for path in _PACKS_DIR.glob("*.yaml"))


def load_policy_pack(pack_id: str) -> PolicyPack:
    normalized_pack_id = str(pack_id).strip()
    # Validate pack_id against canonical list BEFORE constructing a file path
    # to prevent path traversal via crafted pack_id values.
    if normalized_pack_id not in POLICY_PACK_IDS:
        raise ValueError(f"unknown policy pack id: {normalized_pack_id}")
    path = _PACKS_DIR / f"{normalized_pack_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"policy pack not found: {normalized_pack_id}")

    parsed_pack = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    raw_pack = _coerce_string_key_dict(parsed_pack)
    if raw_pack is None:
        raise ValueError(f"policy pack must be a mapping: {path}")

    errors = validate_policy_pack(raw_pack)
    if errors:
        raise ValueError(f"invalid policy pack {normalized_pack_id}: {'; '.join(errors)}")

    return {
        "id": cast(str, raw_pack["id"]),
        "description": cast(str, raw_pack["description"]),
        "tool_restrictions": cast(list[str], raw_pack["tool_restrictions"]),
        "network_posture": cast(Literal["open", "restricted", "airgapped"], raw_pack["network_posture"]),
        "approval_threshold": cast(int, raw_pack["approval_threshold"]),
        "protected_paths": cast(list[str], raw_pack["protected_paths"]),
        "evidence_requirements": cast(list[str], raw_pack["evidence_requirements"]),
        "data_sharing": cast(Literal["allowed", "restricted", "prohibited"], raw_pack["data_sharing"]),
    }


def validate_policy_pack(pack: dict[str, object]) -> list[str]:
    errors: list[str] = []

    for field in _REQUIRED_FIELDS:
        if field not in pack:
            errors.append(f"missing required field: {field}")

    pack_id = str(pack.get("id", "")).strip()
    if not pack_id:
        errors.append("id must be a non-empty string")
    else:
        if pack_id in CANONICAL_PRESETS:
            errors.append(f"id collides with canonical preset: {pack_id}")
        if pack_id in RELEASE_CHANNELS:
            errors.append(f"id collides with release channel: {pack_id}")
        if pack_id in SUBSCRIPTION_TIERS:
            errors.append(f"id collides with subscription tier: {pack_id}")
        if pack_id not in POLICY_PACK_IDS:
            errors.append(f"id is not a canonical policy pack id: {pack_id}")

    description = pack.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("description must be a non-empty string")

    tool_restrictions = pack.get("tool_restrictions")
    if not _is_string_list(tool_restrictions):
        errors.append("tool_restrictions must be a list[str]")

    network_posture = pack.get("network_posture")
    if network_posture not in _VALID_NETWORK_POSTURES:
        errors.append("network_posture must be one of: open, restricted, airgapped")

    approval_threshold = pack.get("approval_threshold")
    if not isinstance(approval_threshold, int):
        errors.append("approval_threshold must be an int")
    elif approval_threshold < 1:
        errors.append("approval_threshold must be >= 1")

    protected_paths = pack.get("protected_paths")
    if not _is_string_list(protected_paths):
        errors.append("protected_paths must be a list[str]")

    evidence_requirements = pack.get("evidence_requirements")
    if not _is_string_list(evidence_requirements):
        errors.append("evidence_requirements must be a list[str]")

    data_sharing = pack.get("data_sharing")
    if data_sharing not in _VALID_DATA_SHARING:
        errors.append("data_sharing must be one of: allowed, restricted, prohibited")

    return errors


def _is_string_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    items = cast(list[object], value)
    for item in items:
        if not isinstance(item, str):
            return False
    return True


def _coerce_string_key_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None

    source = cast(dict[object, object], value)
    result: dict[str, object] = {}
    for key, item in source.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result
