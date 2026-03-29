"""Runtime feature registry for defense and verification controls."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypedDict, cast

DEFAULT_FEATURE_REGISTRY_PATH = Path(".omg") / "state" / "feature-registry.json"
_logger = logging.getLogger(__name__)


class FeatureConfig(TypedDict):
    enabled: bool
    depends_on: list[str]
    description: str


DEFAULT_REGISTRY: dict[str, FeatureConfig] = {
    "DEFENSE_STATE": {
        "enabled": True,
        "depends_on": [],
        "description": "Shared defense-state substrate for runtime policy and hooks.",
    },
    "HOOK_GOVERNOR": {
        "enabled": True,
        "depends_on": ["DEFENSE_STATE"],
        "description": "Enforces canonical lifecycle hook order and fail-closed checks.",
    },
    "TDD_ENFORCEMENT": {
        "enabled": True,
        "depends_on": ["HOOK_GOVERNOR", "DEFENSE_STATE"],
        "description": "Controls tdd-gate ordering and strict red-green-refactor constraints.",
    },
    "VERIFICATION_CONTROLLER": {
        "enabled": True,
        "depends_on": ["DEFENSE_STATE"],
        "description": "Coordinates runtime verification and policy checkpoints.",
    },
    "INTERACTION_JOURNAL": {
        "enabled": True,
        "depends_on": ["DEFENSE_STATE", "VERIFICATION_CONTROLLER"],
        "description": "Captures deterministic interaction history for replay and audits.",
    },
}


def _normalize_entry(name: str, raw_entry: object) -> FeatureConfig:
    default = DEFAULT_REGISTRY[name]
    if not isinstance(raw_entry, dict):
        return {
            "enabled": default["enabled"],
            "depends_on": list(default["depends_on"]),
            "description": default["description"],
        }

    entry = cast(dict[object, object], raw_entry)

    enabled_obj = entry.get("enabled")
    enabled = enabled_obj if isinstance(enabled_obj, bool) else default["enabled"]

    depends_obj = entry.get("depends_on")
    depends_on: list[str] = []
    if isinstance(depends_obj, list):
        for item in cast(list[object], depends_obj):
            if isinstance(item, str) and item.strip():
                depends_on.append(item)
    if not depends_on:
        depends_on = list(default["depends_on"])

    description_obj = entry.get("description")
    if isinstance(description_obj, str) and description_obj.strip():
        description = description_obj.strip()
    else:
        description = default["description"]

    return {
        "enabled": enabled,
        "depends_on": depends_on,
        "description": description,
    }


def _normalize_registry(raw_payload: object) -> dict[str, FeatureConfig]:
    if not isinstance(raw_payload, dict):
        raw_map: dict[object, object] = {}
    else:
        raw_map = cast(dict[object, object], raw_payload)

    normalized: dict[str, FeatureConfig] = {}
    for name in DEFAULT_REGISTRY:
        normalized[name] = _normalize_entry(name, raw_map.get(name))
    return normalized


def load_registry(project_dir: str) -> dict[str, FeatureConfig]:
    root = Path(project_dir)
    registry_path = root / DEFAULT_FEATURE_REGISTRY_PATH
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    if registry_path.exists():
        try:
            raw_payload: object = cast(object, json.loads(registry_path.read_text(encoding="utf-8")))
        except Exception as exc:
            _logger.debug("Failed to parse feature registry at %s: %s", registry_path, exc, exc_info=True)
            raw_payload = {}
    else:
        raw_payload = {}

    normalized = _normalize_registry(raw_payload)
    _ = registry_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=True), encoding="utf-8")
    return normalized
