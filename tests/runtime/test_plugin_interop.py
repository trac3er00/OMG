from __future__ import annotations

import pytest

from runtime.plugin_interop import (
    CONFLICT_SEVERITY_MAP,
    INTEROP_RECORD_SCHEMA,
    ConflictCode,
    ConflictSeverity,
    PluginInteropRecord,
)


def test_record_happy_path_with_all_fields() -> None:
    record = PluginInteropRecord(
        plugin_id="demo-plugin",
        layer="authored",
        host="claude",
        source="plugin_manifest",
        commands=["/OMG:demo"],
        hook_events=["PreToolUse"],
        mcp_servers=["omg-control"],
        preset_floor="balanced",
        enabled=False,
        source_path="plugins/demo/plugin.json",
        metadata={"owner": "team-interop"},
    )

    assert record.plugin_id == "demo-plugin"
    assert record.layer == "authored"
    assert record.host == "claude"
    assert record.source == "plugin_manifest"
    assert record.commands == ["/OMG:demo"]
    assert record.hook_events == ["PreToolUse"]
    assert record.mcp_servers == ["omg-control"]
    assert record.preset_floor == "balanced"
    assert record.enabled is False
    assert record.source_path == "plugins/demo/plugin.json"
    assert record.metadata == {"owner": "team-interop"}


def test_record_to_dict_from_dict_round_trip() -> None:
    initial = PluginInteropRecord(
        plugin_id="demo",
        layer="compiled",
        host="codex",
        source="compiled_bundle",
        commands=["/OMG:setup"],
        hook_events=["PreToolUse", "PostToolUse"],
        mcp_servers=["omg-control", "filesystem"],
        preset_floor="interop",
        enabled=True,
        source_path="dist/plugins/demo.json",
        metadata={"version": "1.0.0"},
    )

    payload = initial.to_dict()
    restored = PluginInteropRecord.from_dict(payload)

    assert payload["layer"] == "compiled"
    assert payload["source"] == "compiled_bundle"
    assert restored == initial


def test_record_invalid_layer_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Invalid layer"):
        _ = PluginInteropRecord(
            plugin_id="demo",
            layer="bad-layer",
            host="claude",
            source="plugin_manifest",
        )


def test_record_invalid_source_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Invalid source"):
        _ = PluginInteropRecord(
            plugin_id="demo",
            layer="authored",
            host="claude",
            source="bad-source",
        )


def test_code_catalog_conflict_codes_are_stable_strings() -> None:
    expected_values = {
        "mcp_name_collision",
        "command_collision",
        "hook_order_violation",
        "preset_escalation",
        "identity_drift",
        "unsupported_host",
        "stale_compiled_artifact",
        "partial_install",
        "host_precedence_overlap",
    }

    actual_values = {code.value for code in ConflictCode}
    assert actual_values == expected_values
    assert all(isinstance(code.value, str) for code in ConflictCode)


def test_code_catalog_severity_map_covers_all_conflict_codes() -> None:
    assert set(CONFLICT_SEVERITY_MAP.keys()) == set(ConflictCode)
    assert CONFLICT_SEVERITY_MAP[ConflictCode.MCP_NAME_COLLISION] == ConflictSeverity.BLOCKER
    assert CONFLICT_SEVERITY_MAP[ConflictCode.PRESET_ESCALATION] == ConflictSeverity.WARNING
    assert CONFLICT_SEVERITY_MAP[ConflictCode.PARTIAL_INSTALL] == ConflictSeverity.INFO


def test_schema_interop_record_schema_shape() -> None:
    assert isinstance(INTEROP_RECORD_SCHEMA, dict)
    assert INTEROP_RECORD_SCHEMA.get("type") == "object"
