from __future__ import annotations

from pathlib import Path


def test_setup_wizard_detects_registered_clis(monkeypatch):
    import hooks.setup_wizard as setup_wizard

    class _FakeProvider:
        def __init__(self, detected: bool, auth_ok):
            self._detected = detected
            self._auth_ok = auth_ok

        def detect(self):
            return self._detected

        def check_auth(self):
            return self._auth_ok

    providers = {
        "codex": _FakeProvider(True, (None, "auth status check not supported")),
        "gemini": _FakeProvider(True, (None, "auth status check not supported")),
        "opencode": _FakeProvider(True, (True, "auth probe succeeded")),
        "kimi": _FakeProvider(False, (None, "")),
    }

    monkeypatch.setattr(setup_wizard, "list_available_providers", lambda: list(providers))
    monkeypatch.setattr(setup_wizard, "get_provider", lambda name: providers.get(name))

    detected = setup_wizard.detect_clis()

    assert detected["codex"]["detected"] is True
    assert detected["gemini"]["detected"] is True
    assert detected["opencode"]["detected"] is True
    assert detected["kimi"]["detected"] is False
    assert "legacy-provider" not in detected


def test_setup_wizard_configure_mcp_writes_detected_provider_configs(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import hooks.setup_wizard as setup_wizard

    detected = {
        "codex": {"detected": True},
        "gemini": {"detected": True},
        "opencode": {"detected": True},
        "kimi": {"detected": False},
    }

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = setup_wizard.configure_mcp(str(project_dir), detected, "http://127.0.0.1:8765/mcp", "omg-memory")

    assert result["status"] == "ok"
    assert set(result["configured"]) == {"codex", "gemini", "opencode"}
    assert (project_dir / ".mcp.json").exists()
    assert (tmp_path / ".codex" / "config.toml").exists()
    assert (tmp_path / ".gemini" / "settings.json").exists()
    assert (tmp_path / ".config" / "opencode" / "opencode.json").exists()


def test_setup_wizard_set_preferences_writes_cli_config(tmp_path):
    import hooks.setup_wizard as setup_wizard

    result = setup_wizard.set_preferences(
        str(tmp_path),
        {"cli_configs": {"codex": {"subscription": "pro", "max_parallel_agents": 3}}},
    )

    config_path = Path(result["path"])
    assert result["status"] == "ok"
    assert config_path.exists()
    assert result["config"]["cli_configs"]["codex"]["subscription"] == "pro"
    assert set(result["config"]["cli_configs"]) == {"codex", "gemini", "opencode", "kimi"}


def test_setup_wizard_run_includes_provider_bootstrap_and_status(tmp_path, monkeypatch):
    import hooks.setup_wizard as setup_wizard

    monkeypatch.setattr(setup_wizard, "is_setup_enabled", lambda: True)
    monkeypatch.setattr(setup_wizard, "detect_clis", lambda: {"codex": {"detected": True}})
    monkeypatch.setattr(setup_wizard, "check_auth", lambda: {"status": "pending", "results": {}})
    monkeypatch.setattr(
        setup_wizard,
        "bootstrap_provider_hosts",
        lambda project_dir, providers=None, server_url=None, server_name="omg-memory": {
            "schema": "ProviderBootstrapResult",
            "status": "ok",
            "configured": ["codex"],
            "written_paths": [str(tmp_path / ".mcp.json")],
        },
    )
    monkeypatch.setattr(
        setup_wizard,
        "collect_provider_status_with_options",
        lambda project_dir, providers=None, include_smoke=False, smoke_host_mode="claude_dispatch": {
            "schema": "ProviderStatusMatrix",
            "status": "ok",
            "providers": [
                {
                    "provider": "codex",
                    "native_ready": True,
                    "local_steps": [],
                    "provider_steps": [],
                    "native_ready_reasons": [],
                }
            ],
        },
    )
    monkeypatch.setattr(
        setup_wizard,
        "set_preferences",
        lambda project_dir, prefs: {"status": "ok", "path": str(tmp_path / "cli-config.yaml"), "config": {}},
    )

    result = setup_wizard.run_setup_wizard(str(tmp_path), non_interactive=True)

    assert result["status"] == "complete"
    assert result["provider_bootstrap"]["schema"] == "ProviderBootstrapResult"
    assert result["provider_status"]["schema"] == "ProviderStatusMatrix"
    assert result["provider_status"]["providers"][0]["local_steps"] == []
    assert result["provider_status"]["providers"][0]["provider_steps"] == []
    assert "entrypoints" in result["provider_status"]["providers"][0]
    assert "host_capabilities" in result["provider_status"]["providers"][0]
