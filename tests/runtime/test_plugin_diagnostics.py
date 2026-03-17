from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import json

from runtime.plugin_diagnostics import (
    approve_plugin,
    check_allowlist_completeness,
    run_plugin_diagnostics,
)


def test_run_plugin_diagnostics_returns_schema() -> None:
    result = run_plugin_diagnostics(root=None, live=False)
    assert result["schema"] == "PluginDiagnosticsResult"


def test_run_plugin_diagnostics_has_required_keys() -> None:
    result = run_plugin_diagnostics(root=None, live=False)
    required = {
        "schema",
        "status",
        "records",
        "conflicts",
        "approval_states",
        "summary",
        "next_actions",
        "elapsed_ms",
    }
    assert required.issubset(result.keys())


def test_run_plugin_diagnostics_elapsed_ms(tmp_path: Path) -> None:
    result = run_plugin_diagnostics(root=str(tmp_path), live=False)
    elapsed_raw = result["elapsed_ms"]
    assert isinstance(elapsed_raw, (int, float))
    elapsed_ms = float(elapsed_raw)
    assert elapsed_ms >= 0


def test_approve_plugin_unknown_source_rejected(tmp_path: Path) -> None:
    result = approve_plugin("mcp:missing", "claude", "bad", str(tmp_path))

    assert result["schema"] == "ApprovalResult"
    assert result["status"] == "error"


def test_approve_plugin_valid_source_approved(tmp_path: Path) -> None:
    _ = (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "npx"}}}),
        encoding="utf-8",
    )

    result = approve_plugin("mcp:filesystem", "claude", "trusted", str(tmp_path))

    assert result["status"] == "ok"
    allowlist_path = tmp_path / ".omg" / "state" / "plugins-allowlist.yaml"
    assert allowlist_path.exists()


def test_run_plugin_diagnostics_live_false_no_probing(tmp_path: Path) -> None:
    result = run_plugin_diagnostics(root=str(tmp_path), live=False)

    assert "live_probe_results" not in result


def test_run_plugin_diagnostics_live_true_has_probe_results(tmp_path: Path) -> None:
    _ = (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"test-mcp": {"command": "echo", "args": ["hi"]}}}),
        encoding="utf-8",
    )

    mock_probe_result = {
        "server": "test-mcp",
        "status": "ok",
        "tools": [],
        "elapsed_ms": 42.0,
    }

    with patch(
        "runtime.plugin_diagnostics.plugin_interop.probe_mcp_server_live",
        return_value=mock_probe_result,
    ):
        result = run_plugin_diagnostics(root=str(tmp_path), live=True)

    assert "live_probe_results" in result
    probe_results = result["live_probe_results"]
    assert isinstance(probe_results, list)
    assert any(p["server"] == "test-mcp" for p in probe_results)


def _write_mcp_json(path: Path, servers: dict[str, object]) -> None:
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _write_allowlist(tmp_path: Path, entries: list[dict[str, str]]) -> None:
    import yaml

    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(entries, sort_keys=False)
    assert isinstance(dumped, str)
    (state_dir / "plugins-allowlist.yaml").write_text(dumped, encoding="utf-8")


def test_check_allowlist_completeness_empty_allowlist(tmp_path: Path) -> None:
    _write_mcp_json(
        tmp_path / ".mcp.json",
        {"filesystem": {"command": "npx"}, "omg-control": {"command": "python3"}},
    )

    result = check_allowlist_completeness(str(tmp_path))

    assert result["complete"] is False
    assert result["allowlisted_count"] == 0
    assert result["checked_count"] == 2
    missing = result["missing_approvals"]
    assert isinstance(missing, list)
    assert "mcp:filesystem@claude" in missing
    assert "mcp:omg-control@claude" in missing


def test_check_allowlist_completeness_complete(tmp_path: Path) -> None:
    _write_mcp_json(
        tmp_path / ".mcp.json",
        {"filesystem": {"command": "npx"}, "omg-control": {"command": "python3"}},
    )
    _write_allowlist(tmp_path, [
        {"source": "mcp:filesystem", "host": "claude", "resource_type": "mcp_server", "reason": "trusted"},
        {"source": "mcp:omg-control", "host": "claude", "resource_type": "mcp_server", "reason": "trusted"},
    ])

    result = check_allowlist_completeness(str(tmp_path))

    assert result["complete"] is True
    assert result["missing_approvals"] == []
    assert result["allowlisted_count"] == 2
    assert result["checked_count"] == 2


def test_check_allowlist_completeness_partial(tmp_path: Path) -> None:
    _write_mcp_json(
        tmp_path / ".mcp.json",
        {"filesystem": {"command": "npx"}, "omg-control": {"command": "python3"}},
    )
    _write_allowlist(tmp_path, [
        {"source": "mcp:filesystem", "host": "claude", "resource_type": "mcp_server", "reason": "trusted"},
    ])

    result = check_allowlist_completeness(str(tmp_path))

    assert result["complete"] is False
    assert result["missing_approvals"] == ["mcp:omg-control@claude"]
    assert result["allowlisted_count"] == 1
    assert result["checked_count"] == 2


def test_check_allowlist_completeness_no_mcp_config(tmp_path: Path) -> None:
    result = check_allowlist_completeness(str(tmp_path))

    assert result["complete"] is True
    assert result["missing_approvals"] == []
    assert result["checked_count"] == 0


def test_check_allowlist_completeness_deduplicates_across_configs(tmp_path: Path) -> None:
    _write_mcp_json(tmp_path / ".mcp.json", {"omg-control": {"command": "python3"}})
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    _write_mcp_json(plugin_dir / "mcp.json", {"omg-control": {"command": "python3"}})

    result = check_allowlist_completeness(str(tmp_path))

    assert result["checked_count"] == 1
    assert result["missing_approvals"] == ["mcp:omg-control@claude"]


def test_approve_plugin_then_allowlist_complete(tmp_path: Path) -> None:
    _write_mcp_json(tmp_path / ".mcp.json", {"omg-control": {"command": "python3"}})

    before = check_allowlist_completeness(str(tmp_path))
    assert before["complete"] is False

    approval = approve_plugin("mcp:omg-control", "claude", "OMG managed", str(tmp_path))
    assert approval["status"] == "ok"

    after = check_allowlist_completeness(str(tmp_path))
    assert after["complete"] is True
    assert after["missing_approvals"] == []


def test_run_plugin_diagnostics_includes_allowlist_completeness(tmp_path: Path) -> None:
    result = run_plugin_diagnostics(root=str(tmp_path), live=False)

    assert "allowlist_completeness" in result
    completeness = result["allowlist_completeness"]
    assert isinstance(completeness, dict)
    assert "complete" in completeness
    assert "missing_approvals" in completeness
