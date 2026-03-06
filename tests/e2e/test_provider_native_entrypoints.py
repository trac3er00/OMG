"""Native-host and Claude-dispatch entrypoint parity coverage."""
from __future__ import annotations

from pathlib import Path


def test_collect_provider_status_reports_native_and_dispatch_entrypoints(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text("{}", encoding="utf-8")
    config = tmp_path / ".kimi" / "mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")

    class _FakeProvider:
        def detect(self):
            return True

        def check_auth(self):
            return True, "auth ok"

        def get_config_path(self):
            return str(config)

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: ["kimi"])
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        provider_bootstrap,
        "get_host_runtime_paths",
        lambda host_mode, _project_dir: {
            "host_mode": host_mode,
            "host_config": str(config if host_mode == "kimi_native" else tmp_path / ".claude" / "settings.json"),
            "project_mcp": str(project_dir / ".mcp.json"),
            "bootstrap_root": str(project_dir / ".omg"),
            "omg_entrypoint": str(project_dir / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
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
        provider_bootstrap,
        "run_provider_live_smoke",
        lambda provider_name, project_dir, host_mode="claude_dispatch", prompt="Reply with OK.", timeout=45: {
            "provider": provider_name,
            "host_mode": host_mode,
            "smoke_status": "success",
            "blocking_class": "ready",
            "retryable": True,
            "recovery_action": "none",
            "additional_recovery_actions": [],
            "warning_codes": [],
            "warning_messages": [],
        },
    )

    result = provider_bootstrap.collect_provider_status(str(project_dir), include_smoke=True)

    entry = result["providers"][0]
    assert entry["parity_state"] == "native_ready"
    assert entry["entrypoints"]["native"]["host_mode"] == "kimi_native"
    assert entry["entrypoints"]["native"]["ready"] is True
    assert entry["entrypoints"]["dispatch"]["host_mode"] == "claude_dispatch"
    assert entry["entrypoints"]["dispatch"]["ready"] is True
    assert entry["host_capabilities"]["native"]["tool_calling_supported"] is True
    assert entry["host_capabilities"]["dispatch"]["claude_call_supported"] is True


def test_collect_provider_status_can_report_dispatch_only_entrypoint(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text("{}", encoding="utf-8")

    class _FakeProvider:
        def detect(self):
            return True

        def check_auth(self):
            return True, "auth ok"

        def get_config_path(self):
            return str(tmp_path / ".codex" / "config.toml")

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: ["codex"])
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        provider_bootstrap,
        "get_host_runtime_paths",
        lambda host_mode, _project_dir: {
            "host_mode": host_mode,
            "host_config": str(tmp_path / "missing-config.toml" if host_mode == "codex_native" else tmp_path / ".claude" / "settings.json"),
            "project_mcp": str(project_dir / ".mcp.json"),
            "bootstrap_root": str(project_dir / ".omg"),
            "omg_entrypoint": str(project_dir / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
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
        provider_bootstrap,
        "run_provider_live_smoke",
        lambda provider_name, project_dir, host_mode="claude_dispatch", prompt="Reply with OK.", timeout=45: {
            "provider": provider_name,
            "host_mode": host_mode,
            "smoke_status": "success",
            "blocking_class": "ready",
            "retryable": True,
            "recovery_action": "none",
            "additional_recovery_actions": [],
            "warning_codes": [],
            "warning_messages": [],
        },
    )

    result = provider_bootstrap.collect_provider_status(str(project_dir), include_smoke=True)

    entry = result["providers"][0]
    assert entry["parity_state"] == "dispatch_ready"
    assert entry["entrypoints"]["native"]["ready"] is False
    assert entry["entrypoints"]["dispatch"]["ready"] is True
    assert entry["native_ready_reasons"] == ["host_config_missing"]
    assert entry["dispatch_ready_reasons"] == []
