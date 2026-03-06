from __future__ import annotations

from pathlib import Path


def test_collect_provider_status_reports_readiness(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text("{}", encoding="utf-8")
    codex_config = tmp_path / ".codex" / "config.toml"
    codex_config.parent.mkdir(parents=True)
    codex_config.write_text("[mcp_servers.omg-memory]\n", encoding="utf-8")

    class _FakeProvider:
        def __init__(self, config_path: str, auth_tuple):
            self._config_path = config_path
            self._auth_tuple = auth_tuple

        def detect(self):
            return True

        def check_auth(self):
            return self._auth_tuple

        def get_config_path(self):
            return self._config_path

    providers = {
        "codex": _FakeProvider(str(codex_config), (True, "auth ok")),
        "kimi": _FakeProvider(str(tmp_path / ".kimi" / "config.toml"), (None, "manual auth check")),
    }

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: list(providers))
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: providers.get(name))
    monkeypatch.setattr(
        provider_bootstrap,
        "get_host_runtime_paths",
        lambda host_mode, _project_dir: {
            "host_mode": host_mode,
            "host_config": str(codex_config if host_mode == "codex_native" else tmp_path / ".kimi" / "config.toml"),
            "project_mcp": str(project_dir / ".mcp.json"),
            "bootstrap_root": str(project_dir / ".omg"),
            "omg_entrypoint": str(project_dir / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
        "check_memory_server",
        lambda: {
            "running": True,
            "url": "http://127.0.0.1:8765/mcp",
            "pid": 12,
            "health_ok": True,
            "log_path": str(tmp_path / "server.log"),
        },
    )

    result = provider_bootstrap.collect_provider_status(str(project_dir))

    assert result["schema"] == "ProviderStatusMatrix"
    entries = {entry["provider"]: entry for entry in result["providers"]}
    assert entries["codex"]["detected"] is True
    assert entries["codex"]["native_ready"] is True
    assert entries["codex"]["dispatch_ready"] is True
    assert entries["codex"]["auth_ok"] is True
    assert entries["kimi"]["detected"] is True
    assert entries["kimi"]["native_ready"] is False
    assert entries["kimi"]["manual_steps"]


def test_bootstrap_provider_hosts_writes_configs_and_reports_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    class _FakeProvider:
        def __init__(self, config_path: str):
            self._config_path = config_path

        def detect(self):
            return True

        def check_auth(self):
            return None, "auth status check not supported"

        def get_config_path(self):
            return self._config_path

    providers = {
        "codex": _FakeProvider(str(tmp_path / ".codex" / "config.toml")),
        "kimi": _FakeProvider(str(tmp_path / ".kimi" / "mcp.json")),
    }

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: list(providers))
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: providers.get(name))
    monkeypatch.setattr(
        provider_bootstrap,
        "ensure_memory_server",
        lambda: {
            "status": "started",
            "url": "http://127.0.0.1:8765/mcp",
            "pid": 77,
            "log_path": str(tmp_path / "server.log"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
        "check_memory_server",
        lambda: {
            "running": True,
            "url": "http://127.0.0.1:8765/mcp",
            "pid": 77,
            "health_ok": True,
            "log_path": str(tmp_path / "server.log"),
        },
    )

    result = provider_bootstrap.bootstrap_provider_hosts(str(project_dir), providers=["codex", "kimi"])

    assert result["schema"] == "ProviderBootstrapResult"
    assert result["status"] == "ok"
    assert set(result["configured"]) == {"codex", "kimi"}
    assert (project_dir / ".mcp.json").exists()
    assert (tmp_path / ".codex" / "config.toml").exists()
    assert (tmp_path / ".kimi" / "mcp.json").exists()
    assert result["mcp_server"]["running"] is True
    assert result["written_paths"]


def test_collect_provider_status_with_smoke_includes_live_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text("{}", encoding="utf-8")
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[mcp_servers.omg-memory]\n", encoding="utf-8")

    class _FakeProvider:
        def detect(self):
            return True

        def check_auth(self):
            return None, "auth status check not supported"

        def get_config_path(self):
            return str(config)

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: ["codex"])
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        provider_bootstrap,
        "get_host_runtime_paths",
        lambda host_mode, _project_dir: {
            "host_mode": host_mode,
            "host_config": str(config),
            "project_mcp": str(project_dir / ".mcp.json"),
            "bootstrap_root": str(project_dir / ".omg"),
            "omg_entrypoint": str(project_dir / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
        "check_memory_server",
        lambda: {
            "running": True,
            "url": "http://127.0.0.1:8765/mcp",
            "pid": 12,
            "health_ok": True,
            "log_path": str(tmp_path / "server.log"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
        "run_provider_live_smoke",
        lambda provider_name, project_dir, host_mode="claude_dispatch", prompt="Reply with OK.", timeout=45: {
            "provider": provider_name,
            "host_mode": host_mode,
            "smoke_status": "auth_required",
            "blocking_class": "authentication_required",
            "retryable": True,
            "recovery_action": "login_to_provider",
        },
    )

    result = provider_bootstrap.collect_provider_status(str(project_dir), include_smoke=True)

    entry = result["providers"][0]
    assert entry["live_smoke"]["smoke_status"] == "auth_required"
    assert entry["dispatch_ready"] is False
    assert "login_to_provider" in entry["manual_steps"]


def test_collect_provider_status_with_smoke_includes_codex_warning_steps(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text("{}", encoding="utf-8")
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[mcp_servers.omg-memory]\n", encoding="utf-8")

    class _FakeProvider:
        def detect(self):
            return True

        def check_auth(self):
            return None, "auth status check not supported"

        def get_config_path(self):
            return str(config)

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: ["codex"])
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        provider_bootstrap,
        "get_host_runtime_paths",
        lambda host_mode, _project_dir: {
            "host_mode": host_mode,
            "host_config": str(config),
            "project_mcp": str(project_dir / ".mcp.json"),
            "bootstrap_root": str(project_dir / ".omg"),
            "omg_entrypoint": str(project_dir / "scripts" / "omg.py"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
        "check_memory_server",
        lambda: {
            "running": True,
            "url": "http://127.0.0.1:8765/mcp",
            "pid": 12,
            "health_ok": True,
            "log_path": str(tmp_path / "server.log"),
        },
    )
    monkeypatch.setattr(
        provider_bootstrap,
        "run_provider_live_smoke",
        lambda provider_name, project_dir, host_mode="claude_dispatch", prompt="Reply with OK.", timeout=45: {
            "provider": provider_name,
            "host_mode": host_mode,
            "smoke_status": "auth_required",
            "blocking_class": "authentication_required",
            "retryable": True,
            "recovery_action": "login_to_provider",
            "warning_codes": ["unsupported_feature_flag"],
            "warning_messages": ["unknown feature key in config: rmcp_client"],
            "additional_recovery_actions": ["remove_incompatible_feature_flags"],
        },
    )

    result = provider_bootstrap.collect_provider_status(str(project_dir), include_smoke=True)

    entry = result["providers"][0]
    assert entry["live_smoke"]["warning_codes"] == ["unsupported_feature_flag"]
    assert "login_to_provider" in entry["manual_steps"]
    assert "remove_incompatible_feature_flags" in entry["manual_steps"]


def test_collect_provider_status_splits_gemini_provider_block_from_local_steps(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text("{}", encoding="utf-8")
    config = tmp_path / ".gemini" / "settings.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")

    class _FakeProvider:
        def detect(self):
            return True

        def check_auth(self):
            return None, "auth status check not supported"

        def get_config_path(self):
            return str(config)

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: ["gemini"])
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        provider_bootstrap,
        "get_host_runtime_paths",
        lambda host_mode, _project_dir: {
            "host_mode": host_mode,
            "host_config": str(config),
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
            "smoke_status": "service_disabled",
            "blocking_class": "service_disabled",
            "retryable": False,
            "recovery_action": "appeal_provider_account",
            "warning_codes": [],
            "warning_messages": [],
            "additional_recovery_actions": [],
            "dependency_state": "ready",
        },
    )

    result = provider_bootstrap.collect_provider_status(str(project_dir), include_smoke=True)

    entry = result["providers"][0]
    assert entry["native_ready"] is False
    assert entry["dispatch_ready"] is False
    assert entry["local_steps"] == []
    assert entry["provider_steps"] == ["appeal_provider_account"]
    assert entry["manual_steps"] == ["appeal_provider_account"]
    assert entry["native_ready_reasons"] == ["provider_service_disabled"]
    assert entry["dispatch_ready_reasons"] == ["provider_service_disabled"]


def test_collect_provider_status_can_report_native_ready_without_running_mcp(tmp_path, monkeypatch):
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
            "host_config": str(config),
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

    result = provider_bootstrap.collect_provider_status(str(project_dir))

    entry = result["providers"][0]
    assert entry["native_ready"] is True
    assert entry["dispatch_ready"] is True
    assert entry["local_steps"] == []
    assert entry["provider_steps"] == []
    assert entry["native_ready_reasons"] == []
    assert entry["dispatch_ready_reasons"] == []


def test_repair_provider_hosts_reports_codex_backup_and_removed_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    class _FakeProvider:
        def get_config_path(self):
            return str(tmp_path / ".codex" / "config.toml")

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: ["codex"])
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        provider_bootstrap,
        "write_codex_mcp_config",
        lambda server_url, server_name="omg-memory": {
            "config_path": str(tmp_path / ".codex" / "config.toml"),
            "backup_path": str(tmp_path / ".codex" / "backups" / "config.toml.123.bak"),
            "changed": True,
            "removed_keys": ["rmcp_client"],
        },
    )

    result = provider_bootstrap.repair_provider_hosts(str(project_dir), providers=["codex"])

    assert result["schema"] == "ProviderRepairResult"
    assert result["providers"] == ["codex"]
    assert result["repairs"]["codex"]["changed"] is True
    assert result["repairs"]["codex"]["removed_keys"] == ["rmcp_client"]
    assert result["manual_steps"]["codex"] == ["login_to_provider"]


def test_collect_provider_status_includes_gemini_fallback_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    import runtime.provider_bootstrap as provider_bootstrap

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text("{}", encoding="utf-8")
    config = tmp_path / ".gemini" / "settings.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")

    class _FakeProvider:
        def detect(self):
            return True

        def check_auth(self):
            return None, "auth status check not supported"

        def get_config_path(self):
            return str(config)

    monkeypatch.setattr(provider_bootstrap, "list_available_providers", lambda: ["gemini"])
    monkeypatch.setattr(provider_bootstrap, "get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        provider_bootstrap,
        "get_host_runtime_paths",
        lambda host_mode, _project_dir: {
            "host_mode": host_mode,
            "host_config": str(config),
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
            "smoke_status": "service_disabled",
            "blocking_class": "service_disabled",
            "retryable": False,
            "recovery_action": "appeal_provider_account",
            "fallback_provider": "claude",
            "fallback_reason": "provider_service_disabled",
            "fallback_mode": "provider_failover",
            "fallback_trigger_class": "hard_failure",
            "fallback_execution_path": "claude_native",
            "fallback_decision_source": "team_router",
            "warning_codes": [],
            "warning_messages": [],
            "additional_recovery_actions": [],
            "dependency_state": "ready",
        },
    )

    result = provider_bootstrap.collect_provider_status(str(project_dir), include_smoke=True)

    entry = result["providers"][0]
    assert entry["fallback_provider"] == "claude"
    assert entry["fallback_reason"] == "provider_service_disabled"
    assert entry["fallback_mode"] == "provider_failover"
    assert entry["fallback_trigger_class"] == "hard_failure"
    assert entry["fallback_execution_path"] == "claude_native"
    assert entry["fallback_decision_source"] == "team_router"
