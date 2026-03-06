"""Tests for provider smoke preflight and runtime dependency state."""
from __future__ import annotations

from pathlib import Path

from runtime import provider_smoke


class _FakeProvider:
    def detect(self) -> bool:
        return True

    def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
        return {"model": "fake-cli", "output": "OK", "exit_code": 0}


def test_run_provider_live_smoke_records_ready_dependency_state(tmp_path: Path, monkeypatch):
    host_config = tmp_path / "codex.toml"
    host_config.write_text("[mcp_servers.omg-memory]\n", encoding="utf-8")
    project_mcp = tmp_path / ".mcp.json"
    project_mcp.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        provider_smoke,
        "get_host_execution_profile",
        lambda host_mode: {
            "provider": "codex",
            "host_mode": host_mode,
            "policy_mode": "toc_ok",
            "native_omg_supported": False,
            "claude_call_supported": True,
            "mcp_supported": True,
        },
    )
    monkeypatch.setattr(provider_smoke, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(provider_smoke.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        provider_smoke,
        "get_host_runtime_paths",
        lambda host_mode, project_dir: {
            "host_mode": host_mode,
            "host_config": str(host_config),
            "project_mcp": str(project_mcp),
            "bootstrap_root": str(tmp_path / ".omg"),
            "omg_entrypoint": str(tmp_path / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(provider_smoke, "ensure_memory_server", lambda: {"status": "started", "url": "http://127.0.0.1:8765/mcp"})
    monkeypatch.setattr(
        provider_smoke,
        "check_memory_server",
        lambda: {
            "running": True,
            "url": "http://127.0.0.1:8765/mcp",
            "pid": 321,
            "health_ok": True,
            "log_path": str(tmp_path / "server.log"),
        },
    )
    monkeypatch.setattr(
        provider_smoke,
        "_invoke_provider",
        lambda provider_name, prompt, project_dir, timeout=45: {
            "model": "codex-cli",
            "output": "OK",
            "exit_code": 0,
        },
    )

    result = provider_smoke.run_provider_live_smoke("codex", str(tmp_path), host_mode="claude_dispatch")

    assert result["dependency_state"] == "ready"
    assert result["mcp_server"]["running"] is True
    assert result["bootstrap_state"]["host_config_exists"] is True
    assert result["bootstrap_state"]["project_mcp_exists"] is True
    assert result["blocking_class"] == "ready"
    assert result["recovery_action"] == "none"


def test_run_provider_live_smoke_marks_mcp_dependency_unavailable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        provider_smoke,
        "get_host_execution_profile",
        lambda host_mode: {
            "provider": "kimi",
            "host_mode": host_mode,
            "policy_mode": "manual_review_required",
            "native_omg_supported": False,
            "claude_call_supported": True,
            "mcp_supported": True,
        },
    )
    monkeypatch.setattr(provider_smoke, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(provider_smoke.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        provider_smoke,
        "get_host_runtime_paths",
        lambda host_mode, project_dir: {
            "host_mode": host_mode,
            "host_config": str(tmp_path / "missing-config.json"),
            "project_mcp": str(tmp_path / ".mcp.json"),
            "bootstrap_root": str(tmp_path / ".omg"),
            "omg_entrypoint": str(tmp_path / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(provider_smoke, "ensure_memory_server", lambda: {"status": "error", "message": "boot failed"})
    monkeypatch.setattr(
        provider_smoke,
        "check_memory_server",
        lambda: {
            "running": False,
            "url": None,
            "pid": None,
            "health_ok": False,
            "log_path": str(tmp_path / "server.log"),
        },
    )
    monkeypatch.setattr(
        provider_smoke,
        "_invoke_provider",
        lambda provider_name, prompt, project_dir, timeout=45: {
            "provider": provider_name,
            "error_code": "mcp_unreachable",
            "error": "connection refused",
        },
    )

    result = provider_smoke.run_provider_live_smoke("kimi", str(tmp_path), host_mode="claude_dispatch")

    assert result["dependency_state"] == "startup_failed"
    assert result["mcp_server"]["running"] is False
    assert result["blocking_class"] == "mcp_dependency_unavailable"
    assert result["recovery_action"] == "start_omg_memory_server"
    assert result["bootstrap_state"]["host_config_exists"] is False


def test_run_provider_live_smoke_carries_codex_warning_remediation(tmp_path: Path, monkeypatch):
    host_config = tmp_path / "codex.toml"
    host_config.write_text("[mcp_servers.omg-memory]\n", encoding="utf-8")
    project_mcp = tmp_path / ".mcp.json"
    project_mcp.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        provider_smoke,
        "get_host_execution_profile",
        lambda host_mode: {
            "provider": "codex",
            "host_mode": host_mode,
            "policy_mode": "toc_ok",
            "native_omg_supported": False,
            "claude_call_supported": True,
            "mcp_supported": True,
        },
    )
    monkeypatch.setattr(provider_smoke, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(provider_smoke.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        provider_smoke,
        "get_host_runtime_paths",
        lambda host_mode, project_dir: {
            "host_mode": host_mode,
            "host_config": str(host_config),
            "project_mcp": str(project_mcp),
            "bootstrap_root": str(tmp_path / ".omg"),
            "omg_entrypoint": str(tmp_path / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(provider_smoke, "ensure_memory_server", lambda: {"status": "started", "url": "http://127.0.0.1:8765/mcp"})
    monkeypatch.setattr(
        provider_smoke,
        "check_memory_server",
        lambda: {
            "running": True,
            "url": "http://127.0.0.1:8765/mcp",
            "pid": 321,
            "health_ok": True,
            "log_path": str(tmp_path / "server.log"),
        },
    )
    monkeypatch.setattr(
        provider_smoke,
        "_invoke_provider",
        lambda provider_name, prompt, project_dir, timeout=45: {
            "model": "codex-cli",
            "stderr": "unknown feature key in config: rmcp_client",
            "error_code": "auth_required",
            "blocking_class": "authentication_required",
            "retryable": True,
            "recovery_action": "login_to_provider",
            "warning_codes": ["unsupported_feature_flag"],
            "warning_messages": ["unknown feature key in config: rmcp_client"],
            "additional_recovery_actions": ["remove_incompatible_feature_flags"],
        },
    )

    result = provider_smoke.run_provider_live_smoke("codex", str(tmp_path), host_mode="claude_dispatch")

    assert result["warning_codes"] == ["unsupported_feature_flag"]
    assert result["warning_messages"] == ["unknown feature key in config: rmcp_client"]
    assert result["additional_recovery_actions"] == ["remove_incompatible_feature_flags"]
