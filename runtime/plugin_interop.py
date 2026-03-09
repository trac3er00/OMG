from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections.abc import Mapping
from typing import cast


class Layer(str, Enum):
    AUTHORED = "authored"
    COMPILED = "compiled"
    LIVE = "live"
    DISCOVERED = "discovered"


class Source(str, Enum):
    PLUGIN_MANIFEST = "plugin_manifest"
    MCP_JSON = "mcp_json"
    COMPILED_BUNDLE = "compiled_bundle"
    SKILL_REGISTRY = "skill_registry"
    HOST_CONFIG = "host_config"
    PLUGIN_DIR = "plugin_dir"


class ConflictCode(str, Enum):
    MCP_NAME_COLLISION = "mcp_name_collision"
    COMMAND_COLLISION = "command_collision"
    HOOK_ORDER_VIOLATION = "hook_order_violation"
    PRESET_ESCALATION = "preset_escalation"
    IDENTITY_DRIFT = "identity_drift"
    UNSUPPORTED_HOST = "unsupported_host"
    STALE_COMPILED_ARTIFACT = "stale_compiled_artifact"
    PARTIAL_INSTALL = "partial_install"
    HOST_PRECEDENCE_OVERLAP = "host_precedence_overlap"


class ConflictSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


CONFLICT_SEVERITY_MAP: dict[ConflictCode, ConflictSeverity] = {
    ConflictCode.MCP_NAME_COLLISION: ConflictSeverity.BLOCKER,
    ConflictCode.HOOK_ORDER_VIOLATION: ConflictSeverity.BLOCKER,
    ConflictCode.COMMAND_COLLISION: ConflictSeverity.BLOCKER,
    ConflictCode.PRESET_ESCALATION: ConflictSeverity.WARNING,
    ConflictCode.IDENTITY_DRIFT: ConflictSeverity.WARNING,
    ConflictCode.UNSUPPORTED_HOST: ConflictSeverity.WARNING,
    ConflictCode.STALE_COMPILED_ARTIFACT: ConflictSeverity.INFO,
    ConflictCode.PARTIAL_INSTALL: ConflictSeverity.INFO,
    ConflictCode.HOST_PRECEDENCE_OVERLAP: ConflictSeverity.INFO,
}


@dataclass(slots=True)
class PluginInteropRecord:
    plugin_id: str
    layer: str
    host: str
    source: str
    commands: list[str] = field(default_factory=list)
    hook_events: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    preset_floor: str | None = None
    enabled: bool = True
    source_path: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        valid_layers = {member.value for member in Layer}
        valid_sources = {member.value for member in Source}
        if self.layer not in valid_layers:
            raise ValueError(f"Invalid layer: {self.layer}. Expected one of {sorted(valid_layers)}")
        if self.source not in valid_sources:
            raise ValueError(f"Invalid source: {self.source}. Expected one of {sorted(valid_sources)}")

    def to_dict(self) -> dict[str, object]:
        return {
            "plugin_id": self.plugin_id,
            "layer": self.layer,
            "host": self.host,
            "source": self.source,
            "commands": list(self.commands),
            "hook_events": list(self.hook_events),
            "mcp_servers": list(self.mcp_servers),
            "preset_floor": self.preset_floor,
            "enabled": self.enabled,
            "source_path": self.source_path,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> PluginInteropRecord:
        commands = _to_str_list(payload.get("commands"), "commands")
        hook_events = _to_str_list(payload.get("hook_events"), "hook_events")
        mcp_servers = _to_str_list(payload.get("mcp_servers"), "mcp_servers")
        metadata = _to_str_object_dict(payload.get("metadata"), "metadata")
        return cls(
            plugin_id=_to_str_required(payload, "plugin_id"),
            layer=_to_str_required(payload, "layer"),
            host=_to_str_required(payload, "host"),
            source=_to_str_required(payload, "source"),
            commands=commands,
            hook_events=hook_events,
            mcp_servers=mcp_servers,
            preset_floor=_to_optional_str(payload.get("preset_floor"), "preset_floor"),
            enabled=_to_bool(payload.get("enabled", True), "enabled"),
            source_path=_to_optional_str(payload.get("source_path"), "source_path"),
            metadata=metadata,
        )


INTEROP_RECORD_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["plugin_id", "layer", "host", "source"],
    "properties": {
        "plugin_id": {"type": "string"},
        "layer": {"type": "string", "enum": [member.value for member in Layer]},
        "host": {"type": "string"},
        "source": {"type": "string", "enum": [member.value for member in Source]},
        "commands": {"type": "array", "items": {"type": "string"}, "default": []},
        "hook_events": {"type": "array", "items": {"type": "string"}, "default": []},
        "mcp_servers": {"type": "array", "items": {"type": "string"}, "default": []},
        "preset_floor": {"type": ["string", "null"], "default": None},
        "enabled": {"type": "boolean", "default": True},
        "source_path": {"type": ["string", "null"], "default": None},
        "metadata": {"type": "object", "default": {}},
    },
}


def _to_str_required(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _to_optional_str(value: object, key: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ValueError(f"{key} must be a string or None")


def _to_bool(value: object, key: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be a boolean")


def _to_str_list(value: object, key: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list of strings")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"{key} must be a list of strings")
        result.append(item)
    return result


def _to_str_object_dict(value: object, key: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    result: dict[str, object] = {}
    for candidate_key, candidate_value in cast(dict[object, object], value).items():
        if not isinstance(candidate_key, str):
            raise ValueError(f"{key} keys must be strings")
        result[candidate_key] = candidate_value
    return result


__all__ = [
    "CONFLICT_SEVERITY_MAP",
    "INTEROP_RECORD_SCHEMA",
    "ConflictCode",
    "ConflictSeverity",
    "Layer",
    "PluginInteropRecord",
    "Source",
]
