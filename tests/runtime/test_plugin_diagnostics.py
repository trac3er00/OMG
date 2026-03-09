from __future__ import annotations

from pathlib import Path

from runtime.plugin_diagnostics import run_plugin_diagnostics


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
