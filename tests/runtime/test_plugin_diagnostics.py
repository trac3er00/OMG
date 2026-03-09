from __future__ import annotations

from pathlib import Path
import json

from runtime.plugin_diagnostics import approve_plugin, run_plugin_diagnostics


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
