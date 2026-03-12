from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast
from unittest.mock import patch, MagicMock

import pytest

from runtime.plugin_interop import (
    CONFLICT_SEVERITY_MAP,
    INTEROP_RECORD_SCHEMA,
    ConflictCode,
    ConflictSeverity,
    HookChainPlan,
    PluginInteropRecord,
    PluginAllowlistEntry,
    approval_status_for_record,
    classify_conflicts,
    discover_host_plugin_state,
    discover_omg_plugin_state,
    get_approval_status_for_all,
    plan_hook_chain,
    probe_mcp_server_live,
)
from runtime.plugin_diagnostics import approve_plugin, run_plugin_diagnostics


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


def test_discovery_claude_authored_from_fixture(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "core"
    plugin_dir.mkdir(parents=True)
    _ = (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": "omg-core",
                "commands": {
                    "/OMG:setup": {},
                    "setup": {},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = discover_omg_plugin_state(str(tmp_path))

    assert any(
        record.host == "claude" and record.layer == "authored" and record.plugin_id == "omg-core"
        for record in payload.records
    )


def test_discovery_claude_mcp_json(tmp_path: Path) -> None:
    _ = (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {"command": "npx"},
                    "omg-control": {"command": "python3"},
                }
            }
        ),
        encoding="utf-8",
    )

    payload = discover_omg_plugin_state(str(tmp_path))

    live_records = [record for record in payload.records if record.layer == "live" and record.source == "mcp_json"]
    assert any(record.host == "claude" and record.plugin_id == "filesystem" for record in live_records)
    assert any(record.plugin_id == "filesystem" and record.mcp_servers == ["filesystem"] for record in live_records)


def test_discovery_missing_compiled_bundle_degrades_gracefully(tmp_path: Path) -> None:
    payload = discover_omg_plugin_state(str(tmp_path))

    assert payload is not None
    assert payload.records == []


def test_discovery_payload_has_elapsed_ms(tmp_path: Path) -> None:
    payload = discover_omg_plugin_state(str(tmp_path))

    assert payload.elapsed_ms >= 0


def test_host_discovery_codex_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    codex_path = tmp_path / ".codex" / "config.toml"
    codex_path.parent.mkdir(parents=True)
    _ = codex_path.write_text(
        """
[mcp_servers.filesystem]
enabled = true
command = \"npx\"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = discover_host_plugin_state(str(tmp_path))

    assert any(
        record.host == "codex"
        and record.layer == "live"
        and record.source == "host_config"
        and record.plugin_id == "filesystem"
        and record.mcp_servers == ["filesystem"]
        for record in payload.records
    )


def test_host_discovery_gemini_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    gemini_path = tmp_path / ".gemini" / "settings.json"
    gemini_path.parent.mkdir(parents=True)
    _ = gemini_path.write_text(
        json.dumps({"mcpServers": {"omg-control": {"httpUrl": "http://localhost:5050"}}}),
        encoding="utf-8",
    )

    payload = discover_host_plugin_state(str(tmp_path))

    assert any(record.host == "gemini" and record.plugin_id == "omg-control" for record in payload.records)


def test_host_discovery_kimi_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kimi_path = tmp_path / ".kimi" / "mcp.json"
    kimi_path.parent.mkdir(parents=True)
    _ = kimi_path.write_text(
        json.dumps({"mcpServers": {"memory-server": {"type": "http", "url": "http://localhost:9090"}}}),
        encoding="utf-8",
    )

    payload = discover_host_plugin_state(str(tmp_path))

    assert any(record.host == "kimi" and record.plugin_id == "memory-server" for record in payload.records)


def test_host_discovery_opencode_project_config(tmp_path: Path) -> None:
    _ = (tmp_path / "opencode.json").write_text(
        json.dumps({"mcp": {"omg-control": {"type": "stdio", "command": "python3"}}}),
        encoding="utf-8",
    )

    payload = discover_host_plugin_state(str(tmp_path))

    assert any(
        record.host == "opencode"
        and record.layer == "live"
        and record.source == "host_config"
        and record.plugin_id == "omg-control"
        and record.source_path == str(tmp_path / "opencode.json")
        for record in payload.records
    )


def test_host_discovery_opencode_plugin_dir(tmp_path: Path) -> None:
    plugin_path = tmp_path / ".opencode" / "plugins" / "my-plugin"
    plugin_path.mkdir(parents=True)

    payload = discover_host_plugin_state(str(tmp_path))

    assert any(
        record.host == "opencode"
        and record.layer == "discovered"
        and record.source == "plugin_dir"
        and record.plugin_id == "my-plugin"
        for record in payload.records
    )


def test_host_discovery_disabled_entry_included(tmp_path: Path) -> None:
    _ = (tmp_path / "opencode.json").write_text(
        json.dumps({"mcp": {"disabled-server": {"enabled": False, "command": "python3"}}}),
        encoding="utf-8",
    )

    payload = discover_host_plugin_state(str(tmp_path))
    disabled_records = [record for record in payload.records if record.plugin_id == "disabled-server"]

    assert disabled_records
    assert disabled_records[0].enabled is False


def test_host_discovery_missing_configs_degrade_gracefully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    payload = discover_host_plugin_state(str(tmp_path))

    assert payload is not None


def test_collision_mcp_name_same_host() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="plugin-a",
            layer="live",
            host="claude",
            source="mcp_json",
            mcp_servers=["filesystem"],
        ),
        PluginInteropRecord(
            plugin_id="plugin-b",
            layer="live",
            host="claude",
            source="mcp_json",
            mcp_servers=["filesystem"],
        ),
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "mcp_name_collision" and conflict.severity == "blocker" for conflict in conflicts)


def test_collision_command_same_host() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="plugin-a",
            layer="authored",
            host="claude",
            source="plugin_manifest",
            commands=["/OMG:setup"],
        ),
        PluginInteropRecord(
            plugin_id="plugin-b",
            layer="authored",
            host="claude",
            source="plugin_manifest",
            commands=["/OMG:setup"],
        ),
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "command_collision" and conflict.severity == "blocker" for conflict in conflicts)


def test_collision_mcp_name_different_hosts() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="plugin-a",
            layer="live",
            host="claude",
            source="mcp_json",
            mcp_servers=["filesystem"],
        ),
        PluginInteropRecord(
            plugin_id="plugin-b",
            layer="live",
            host="codex",
            source="host_config",
            mcp_servers=["filesystem"],
        ),
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "host_precedence_overlap" and conflict.severity == "info" for conflict in conflicts)
    assert not any(conflict.code == "mcp_name_collision" for conflict in conflicts)


def test_ownership_identity_drift() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="omg-core",
            layer="authored",
            host="claude",
            source="plugin_manifest",
        ),
        PluginInteropRecord(
            plugin_id="omg-core",
            layer="compiled",
            host="claude",
            source="compiled_bundle",
        ),
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "identity_drift" and conflict.severity == "warning" for conflict in conflicts)


def test_ownership_unsupported_host() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="omg-core",
            layer="authored",
            host="unknown-host",
            source="plugin_manifest",
        )
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "unsupported_host" and conflict.severity == "warning" for conflict in conflicts)


def test_ownership_preset_escalation() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="omg-core",
            layer="authored",
            host="claude",
            source="plugin_manifest",
            preset_floor="labs",
        )
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "preset_escalation" and conflict.severity == "warning" for conflict in conflicts)


def test_ownership_preset_escalation_accepts_buffet_floor() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="omg-core",
            layer="authored",
            host="codex",
            source="plugin_manifest",
            preset_floor="buffet",
        )
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "preset_escalation" and conflict.severity == "warning" for conflict in conflicts)


def test_ownership_partial_install() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="omg-core",
            layer="authored",
            host="claude",
            source="plugin_manifest",
        )
    ]

    conflicts = classify_conflicts(records)

    assert any(conflict.code == "partial_install" and conflict.severity == "info" for conflict in conflicts)


def test_classify_conflicts_empty_list() -> None:
    assert classify_conflicts([]) == []


def test_classify_conflicts_no_conflicts() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="firewall",
            layer="authored",
            host="claude",
            source="plugin_manifest",
            hook_events=["PreToolUse"],
            commands=["/OMG:firewall"],
        ),
        PluginInteropRecord(
            plugin_id="secret-guard",
            layer="authored",
            host="claude",
            source="plugin_manifest",
            hook_events=["PreToolUse"],
            commands=["/OMG:secret-guard"],
        ),
        PluginInteropRecord(
            plugin_id="planner",
            layer="authored",
            host="claude",
            source="plugin_manifest",
            commands=["/OMG:plan"],
        ),
    ]

    assert classify_conflicts(records) == []


def test_hook_chain_valid_order() -> None:
    plan = plan_hook_chain("PreToolUse", ["plugin-hook"])

    assert isinstance(plan, HookChainPlan)
    assert plan.event == "PreToolUse"
    assert plan.status == "ok"
    assert plan.blockers == []
    assert plan.chain[:3] == ["firewall", "secret-guard", "plugin-hook"]


def test_hook_chain_foreign_before_firewall_blocked() -> None:
    plan = plan_hook_chain("PreToolUse", ["plugin-hook", "firewall"])

    assert plan.event == "PreToolUse"
    assert plan.status == "blocked"
    assert any("must not appear before" in blocker for blocker in plan.blockers)


def test_hook_chain_non_pretooluse_event() -> None:
    plan = plan_hook_chain("PostToolUse", ["plugin-hook", "cleanup-hook"])

    assert plan.event == "PostToolUse"
    assert plan.status == "ok"
    assert plan.blockers == []
    assert plan.chain == ["plugin-hook", "cleanup-hook"]


def test_approval_state_approved_mcp_server() -> None:
    record = PluginInteropRecord(
        plugin_id="filesystem",
        layer="live",
        host="claude",
        source="mcp_json",
        mcp_servers=["filesystem"],
    )
    approvals = [
        PluginAllowlistEntry(
            source="mcp:filesystem",
            host="claude",
            resource_type="mcp_server",
            reason="allow known filesystem server",
        )
    ]

    assert approval_status_for_record(record, approvals) == "approved"


def test_approval_state_discoverable_known_host() -> None:
    record = PluginInteropRecord(
        plugin_id="demo-plugin",
        layer="authored",
        host="codex",
        source="plugin_manifest",
    )

    assert approval_status_for_record(record, approvals=[]) == "discoverable"


def test_approval_state_blocked_unknown_host() -> None:
    record = PluginInteropRecord(
        plugin_id="demo-plugin",
        layer="live",
        host="unknown-host",
        source="host_config",
    )

    assert approval_status_for_record(record, approvals=[]) == "blocked"


def test_approval_state_unapproved_foreign_mcp() -> None:
    record = PluginInteropRecord(
        plugin_id="github",
        layer="live",
        host="gemini",
        source="host_config",
        mcp_servers=["github"],
    )

    assert approval_status_for_record(record, approvals=[]) == "discoverable"


def test_get_approval_status_for_all() -> None:
    records = [
        PluginInteropRecord(
            plugin_id="filesystem",
            layer="live",
            host="claude",
            source="mcp_json",
            mcp_servers=["filesystem"],
        ),
        PluginInteropRecord(
            plugin_id="draft-plugin",
            layer="authored",
            host="codex",
            source="plugin_manifest",
        ),
        PluginInteropRecord(
            plugin_id="mystery-plugin",
            layer="live",
            host="unknown-host",
            source="host_config",
        ),
    ]
    approvals = [
        PluginAllowlistEntry(
            source="mcp:filesystem",
            host="claude",
            resource_type="mcp_server",
            reason="allow known filesystem server",
        )
    ]

    assert get_approval_status_for_all(records, approvals) == {
        "filesystem": "approved",
        "draft-plugin": "discoverable",
        "mystery-plugin": "blocked",
    }


def test_approve_flow_updates_diagnosis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    _ = (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "npx"}}}),
        encoding="utf-8",
    )

    result = approve_plugin("mcp:filesystem", "claude", "trusted", str(tmp_path))
    assert result["status"] == "ok"

    diagnosis = run_plugin_diagnostics(str(tmp_path))
    approval_states = cast(dict[str, str], diagnosis["approval_states"])
    assert approval_states["filesystem"] == "approved"


def test_live_probe_timeout_handled() -> None:
    mock_proc = MagicMock()
    mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd=["fake"], timeout=1.5)
    mock_proc.kill.return_value = None

    with patch("runtime.plugin_interop.subprocess.Popen", return_value=mock_proc):
        result = probe_mcp_server_live("test-server", ["fake-cmd"], timeout_ms=100)

    assert result["server"] == "test-server"
    assert result["status"] == "timeout"
    assert isinstance(result["elapsed_ms"], float)
    assert result["elapsed_ms"] >= 0
    mock_proc.kill.assert_called_once()


def test_live_probe_error_handled() -> None:
    with patch(
        "runtime.plugin_interop.subprocess.Popen",
        side_effect=FileNotFoundError("No such file: 'nonexistent'"),
    ):
        result = probe_mcp_server_live("bad-server", ["nonexistent"], timeout_ms=500)

    assert result["server"] == "bad-server"
    assert result["status"] == "error"
    assert "error" in result
    assert isinstance(result["error"], str)
    assert isinstance(result["elapsed_ms"], float)
