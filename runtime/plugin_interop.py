from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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


@dataclass(slots=True)
class PluginInteropPayload:
    records: list[PluginInteropRecord]
    elapsed_ms: float
    root: str


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


def discover_omg_plugin_state(root: str | None = None) -> PluginInteropPayload:
    started = time.monotonic()
    root_path = Path(root or ".").resolve()
    records: list[PluginInteropRecord] = []

    for manifest_path in root_path.glob("plugins/*/plugin.json"):
        _append_plugin_manifest_record(records, manifest_path, layer=Layer.AUTHORED)

    _append_plugin_manifest_record(records, root_path / ".claude-plugin" / "plugin.json", layer=Layer.AUTHORED)

    for mcp_path in (root_path / ".claude-plugin" / "mcp.json", root_path / ".mcp.json"):
        records.extend(_records_from_mcp_config(mcp_path))

    records.extend(_records_from_skill_registry(root_path / ".omg" / "state" / "skill_registry" / "compact.json"))

    build_lib_dir = root_path / "build" / "lib"
    if build_lib_dir.is_dir():
        for compiled_manifest_path in build_lib_dir.rglob("plugin.json"):
            _append_plugin_manifest_record(records, compiled_manifest_path, layer=Layer.COMPILED)

    elapsed_ms = (time.monotonic() - started) * 1000.0
    return PluginInteropPayload(records=records, elapsed_ms=elapsed_ms, root=str(root_path))


def discover_host_plugin_state(root: str | None = None) -> PluginInteropPayload:
    started = time.monotonic()
    root_path = Path(root or ".").resolve()
    home_path = Path.home()
    records: list[PluginInteropRecord] = []

    records.extend(_records_from_codex_config(home_path / ".codex" / "config.toml"))
    records.extend(_records_from_host_json_config(home_path / ".gemini" / "settings.json", host="gemini", mcp_key="mcpServers"))
    records.extend(_records_from_host_json_config(home_path / ".kimi" / "mcp.json", host="kimi", mcp_key="mcpServers"))
    records.extend(
        _records_from_host_json_config(
            home_path / ".config" / "opencode" / "opencode.json",
            host="opencode",
            mcp_key="mcp",
        )
    )
    records.extend(_records_from_host_json_config(root_path / "opencode.json", host="opencode", mcp_key="mcp"))
    records.extend(_records_from_opencode_plugin_dir(root_path / ".opencode" / "plugins"))

    elapsed_ms = (time.monotonic() - started) * 1000.0
    return PluginInteropPayload(records=records, elapsed_ms=elapsed_ms, root=str(root_path))


def _append_plugin_manifest_record(
    records: list[PluginInteropRecord],
    manifest_path: Path,
    *,
    layer: Layer,
) -> None:
    manifest = _read_json_dict(manifest_path)
    if manifest is None:
        return

    commands = _extract_omg_commands(manifest)
    plugin_name = manifest.get("name")
    plugin_id = plugin_name if isinstance(plugin_name, str) and plugin_name else manifest_path.parent.name
    records.append(
        PluginInteropRecord(
            plugin_id=plugin_id,
            layer=layer.value,
            host="claude",
            source=Source.PLUGIN_MANIFEST.value if layer is Layer.AUTHORED else Source.COMPILED_BUNDLE.value,
            commands=commands,
            source_path=str(manifest_path),
        )
    )


def _records_from_mcp_config(mcp_path: Path) -> list[PluginInteropRecord]:
    mcp_config = _read_json_dict(mcp_path)
    if mcp_config is None:
        return []

    mcp_servers = mcp_config.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        return []

    server_names = [name for name in cast(dict[object, object], mcp_servers).keys() if isinstance(name, str)]
    records: list[PluginInteropRecord] = []
    for server_name in server_names:
        records.append(
            PluginInteropRecord(
                plugin_id=server_name,
                layer=Layer.LIVE.value,
                host="claude",
                source=Source.MCP_JSON.value,
                mcp_servers=[server_name],
                source_path=str(mcp_path),
            )
        )
    return records


def _records_from_skill_registry(registry_path: Path) -> list[PluginInteropRecord]:
    payload = _read_json_dict(registry_path)
    if payload is None:
        return []

    skill_ids = _extract_skill_ids(payload)
    return [
        PluginInteropRecord(
            plugin_id=skill_id,
            layer=Layer.COMPILED.value,
            host="claude",
            source=Source.SKILL_REGISTRY.value,
            source_path=str(registry_path),
        )
        for skill_id in skill_ids
    ]


def _records_from_codex_config(config_path: Path) -> list[PluginInteropRecord]:
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    discovered: dict[str, bool] = {}
    active_section: str | None = None
    section_server: str | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue

        if line.startswith("[") and line.endswith("]"):
            active_section = line[1:-1].strip()
            section_server = _codex_server_from_section(active_section)
            if section_server is not None:
                _ = discovered.setdefault(section_server, True)
            continue

        if active_section == "mcp_servers" and "=" in line:
            key, value = line.split("=", 1)
            candidate = _unquote_toml_key(key.strip())
            if candidate:
                _ = discovered.setdefault(candidate, True)
                inline_enabled = _extract_enabled_from_toml_value(value)
                if inline_enabled is not None:
                    discovered[candidate] = inline_enabled
            continue

        if section_server is not None and "=" in line:
            key, value = line.split("=", 1)
            if key.strip() == "enabled":
                enabled = _parse_toml_bool(value)
                if enabled is not None:
                    discovered[section_server] = enabled

    return [
        PluginInteropRecord(
            plugin_id=server_name,
            layer=Layer.LIVE.value,
            host="codex",
            source=Source.HOST_CONFIG.value,
            mcp_servers=[server_name],
            enabled=enabled,
            source_path=str(config_path),
        )
        for server_name, enabled in discovered.items()
    ]


def _records_from_host_json_config(config_path: Path, *, host: str, mcp_key: str) -> list[PluginInteropRecord]:
    payload = _read_json_dict(config_path)
    if payload is None:
        return []

    mcp_obj = payload.get(mcp_key)
    if not isinstance(mcp_obj, dict):
        return []

    records: list[PluginInteropRecord] = []
    for server_name, server_payload in cast(dict[object, object], mcp_obj).items():
        if not isinstance(server_name, str):
            continue
        records.append(
            PluginInteropRecord(
                plugin_id=server_name,
                layer=Layer.LIVE.value,
                host=host,
                source=Source.HOST_CONFIG.value,
                mcp_servers=[server_name],
                enabled=_extract_enabled_from_json_payload(server_payload),
                source_path=str(config_path),
            )
        )
    return records


def _records_from_opencode_plugin_dir(plugin_dir: Path) -> list[PluginInteropRecord]:
    try:
        entries = sorted(plugin_dir.iterdir(), key=lambda item: item.name)
    except OSError:
        return []

    return [
        PluginInteropRecord(
            plugin_id=entry.name,
            layer=Layer.DISCOVERED.value,
            host="opencode",
            source=Source.PLUGIN_DIR.value,
            source_path=str(entry),
        )
        for entry in entries
    ]


def _codex_server_from_section(section_name: str) -> str | None:
    if not section_name.startswith("mcp_servers."):
        return None
    return _unquote_toml_key(section_name[len("mcp_servers.") :].strip())


def _unquote_toml_key(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_toml_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _extract_enabled_from_toml_value(value: str) -> bool | None:
    match = re.search(r"\benabled\s*=\s*(true|false)\b", value, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).lower() == "true"


def _extract_enabled_from_json_payload(payload: object) -> bool:
    if isinstance(payload, bool):
        return payload
    if isinstance(payload, dict):
        enabled = cast(dict[object, object], payload).get("enabled")
        if isinstance(enabled, bool):
            return enabled
    return True


def _extract_omg_commands(payload: Mapping[str, object]) -> list[str]:
    commands = payload.get("commands")
    if not isinstance(commands, dict):
        return []
    return [
        key
        for key in cast(dict[object, object], commands).keys()
        if isinstance(key, str) and key.startswith("/OMG:")
    ]


def _extract_skill_ids(payload: Mapping[str, object]) -> list[str]:
    discovered: list[str] = []

    skills = payload.get("skills")
    if isinstance(skills, list):
        for entry in cast(list[object], skills):
            if isinstance(entry, str):
                discovered.append(entry)
            elif isinstance(entry, dict):
                candidate = cast(dict[object, object], entry).get("id")
                if isinstance(candidate, str):
                    discovered.append(candidate)
    elif isinstance(skills, dict):
        discovered.extend(key for key in cast(dict[object, object], skills).keys() if isinstance(key, str))

    discovered.extend(key for key in payload if key not in {"skills", "schema", "version"})

    deduped: list[str] = []
    seen: set[str] = set()
    for skill_id in discovered:
        if skill_id not in seen:
            seen.add(skill_id)
            deduped.append(skill_id)
    return deduped


def _read_json_dict(path: Path) -> dict[str, object] | None:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        payload_obj = cast(object, json.loads(raw_text))
    except json.JSONDecodeError:
        return None

    if not isinstance(payload_obj, dict):
        return None
    return cast(dict[str, object], payload_obj)


__all__ = [
    "CONFLICT_SEVERITY_MAP",
    "INTEROP_RECORD_SCHEMA",
    "ConflictCode",
    "ConflictSeverity",
    "Layer",
    "PluginInteropPayload",
    "PluginInteropRecord",
    "Source",
    "discover_host_plugin_state",
    "discover_omg_plugin_state",
]
