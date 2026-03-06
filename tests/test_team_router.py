from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest


_MODULE_PATH = Path(__file__).resolve().parents[1] / "runtime" / "team_router.py"
_SPEC = importlib.util.spec_from_file_location("team_router_under_test", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
team_router = importlib.util.module_from_spec(_SPEC)
sys.modules["team_router_under_test"] = team_router
_SPEC.loader.exec_module(team_router)


def test_dispatch_to_model_unknown_agent_returns_error_and_fallback() -> None:
    result = team_router.dispatch_to_model("missing-agent", "do thing", "/tmp/project")

    assert "Unknown agent" in result["error"]
    assert result["fallback"] == "claude"


def test_dispatch_to_model_known_agent_without_cli_returns_claude_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_registry = types.ModuleType("_agent_registry")
    setattr(fake_registry, "AGENT_REGISTRY", {
        "backend-engineer": {
            "preferred_model": "codex-cli",
            "task_category": "deep",
            "skills": ["backend-patterns"],
            "description": "Backend specialist",
        }
    })
    setattr(fake_registry, "detect_available_models", lambda: {
        "claude": True,
        "codex-cli": False,
        "gemini-cli": False,
    })
    monkeypatch.setitem(sys.modules, "_agent_registry", fake_registry)

    result = team_router.dispatch_to_model("backend-engineer", "fix api", "/tmp/project")

    assert result["fallback"] == "claude"
    assert result["category"] == "deep"
    assert result["skills"] == ["backend-patterns"]
    assert result["fallback_provider"] == "claude"
    assert result["fallback_mode"] == "provider_failover"
    assert result["fallback_agent_name"] == "backend-engineer"
    assert result["fallback_model_tier"] == "sonnet"
    assert result["fallback_model_role"] == "default"
    assert result["fallback_preserved_skills"] == ["backend-patterns"]


def test_dispatch_to_model_routes_kimi_cli_via_provider_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_registry = types.ModuleType("_agent_registry")
    setattr(fake_registry, "AGENT_REGISTRY", {
        "local-runtime": {
            "preferred_model": "kimi-cli",
            "task_category": "deep",
            "skills": ["backend-patterns"],
            "description": "Local runtime specialist",
        }
    })
    setattr(fake_registry, "detect_available_models", lambda: {
        "claude": True,
        "codex-cli": False,
        "gemini-cli": False,
        "kimi-cli": True,
    })
    monkeypatch.setitem(sys.modules, "_agent_registry", fake_registry)

    class _FakeProvider:
        def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            return {"model": "kimi-cli", "output": prompt, "exit_code": 0}

        def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            raise AssertionError("tmux should not be used in this test")

    monkeypatch.setattr(team_router, "_get_registered_provider", lambda name: _FakeProvider() if name == "kimi" else None, raising=False)
    monkeypatch.setattr(team_router, "_should_use_tmux", lambda: False)

    result = team_router.dispatch_to_model("local-runtime", "inspect runtime", "/tmp/project")

    assert result["model"] == "kimi-cli"
    assert result["provider"] == "kimi"
    assert result["host_mode"] == "claude_dispatch"


def test_dispatch_to_model_routes_codex_cli_via_provider_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_registry = types.ModuleType("_agent_registry")
    setattr(fake_registry, "AGENT_REGISTRY", {
        "implementation-engineer": {
            "preferred_model": "codex-cli",
            "task_category": "deep",
            "skills": ["backend-patterns"],
            "description": "Implementation specialist",
        }
    })
    setattr(fake_registry, "detect_available_models", lambda: {
        "claude": True,
        "codex-cli": True,
        "gemini-cli": False,
        "kimi-cli": False,
    })
    monkeypatch.setitem(sys.modules, "_agent_registry", fake_registry)

    class _FakeProvider:
        def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            return {"model": "codex-cli", "output": prompt, "exit_code": 0}

        def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            raise AssertionError("tmux should not be used in this test")

    monkeypatch.setattr(team_router, "_get_registered_provider", lambda name: _FakeProvider() if name == "codex" else None, raising=False)
    monkeypatch.setattr(team_router, "_should_use_tmux", lambda: False)

    result = team_router.dispatch_to_model("implementation-engineer", "ship feature", "/tmp/project")

    assert result["model"] == "codex-cli"
    assert result["provider"] == "codex"
    assert result["host_mode"] == "claude_dispatch"


def test_dispatch_to_model_routes_opencode_cli_via_provider_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_registry = types.ModuleType("_agent_registry")
    setattr(fake_registry, "AGENT_REGISTRY", {
        "implementation-engineer": {
            "preferred_model": "opencode-cli",
            "task_category": "deep",
            "skills": ["backend-patterns"],
            "description": "Implementation specialist",
        }
    })
    setattr(fake_registry, "detect_available_models", lambda: {
        "claude": True,
        "codex-cli": False,
        "gemini-cli": False,
        "opencode-cli": True,
        "kimi-cli": False,
    })
    monkeypatch.setitem(sys.modules, "_agent_registry", fake_registry)

    class _FakeProvider:
        def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            return {"model": "opencode-cli", "output": prompt, "exit_code": 0}

        def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            raise AssertionError("tmux should not be used in this test")

    monkeypatch.setattr(team_router, "_get_registered_provider", lambda name: _FakeProvider() if name == "opencode" else None, raising=False)
    monkeypatch.setattr(team_router, "_should_use_tmux", lambda: False)

    result = team_router.dispatch_to_model("implementation-engineer", "ship feature", "/tmp/project")

    assert result["model"] == "opencode-cli"
    assert result["provider"] == "opencode"
    assert result["host_mode"] == "claude_dispatch"


def test_dispatch_to_model_normalizes_kimi_missing_model_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_registry = types.ModuleType("_agent_registry")
    setattr(fake_registry, "AGENT_REGISTRY", {
        "local-runtime": {
            "preferred_model": "kimi-cli",
            "task_category": "deep",
            "skills": [],
            "description": "Local runtime specialist",
        }
    })
    setattr(fake_registry, "detect_available_models", lambda: {
        "claude": True,
        "codex-cli": False,
        "gemini-cli": False,
        "kimi-cli": True,
    })
    monkeypatch.setitem(sys.modules, "_agent_registry", fake_registry)

    class _FakeProvider:
        def invoke(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            return {
                "model": "kimi-cli",
                "output": "",
                "stderr": "LLM not set",
                "exit_code": 1,
            }

        def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120) -> dict[str, object]:
            raise AssertionError("tmux should not be used in this test")

    monkeypatch.setattr(team_router, "_get_registered_provider", lambda name: _FakeProvider() if name == "kimi" else None, raising=False)
    monkeypatch.setattr(team_router, "_should_use_tmux", lambda: False)

    result = team_router.dispatch_to_model("local-runtime", "inspect runtime", "/tmp/project")

    assert result["provider"] == "kimi"
    assert result["host_mode"] == "claude_dispatch"
    assert result["error_code"] == "missing_model"
    assert result["fallback_provider"] == "claude"
    assert result["fallback_mode"] == "provider_failover"
    assert result["fallback_agent_name"] == "local-runtime"
    assert result["fallback_model_tier"] == "sonnet"
    assert result["fallback_model_role"] == "default"


def test_invoke_codex_returns_not_found_when_tool_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(team_router, "_check_tool_available", lambda _name: False)

    result = team_router.invoke_codex("hello", "/tmp/project")

    assert result == {"error": "codex-cli not found", "fallback": "claude"}


def test_invoke_gemini_returns_not_found_when_tool_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(team_router, "_check_tool_available", lambda _name: False)

    result = team_router.invoke_gemini("hello", "/tmp/project")

    assert result == {"error": "gemini-cli not found", "fallback": "claude"}


def test_package_prompt_contains_user_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_registry = types.ModuleType("_agent_registry")
    setattr(fake_registry, "AGENT_REGISTRY", {
        "security-auditor": {"description": "Security specialist"}
    })
    monkeypatch.setitem(sys.modules, "_agent_registry", fake_registry)

    user_prompt = "audit login flow"
    packaged = team_router.package_prompt("security-auditor", user_prompt, "/tmp/project")

    assert isinstance(packaged, str)
    assert user_prompt in packaged


def test_invoke_codex_timeout_returns_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(team_router, "_check_tool_available", lambda _name: True)

    def _raise_timeout(_cmd: list[str], *, timeout: int = 30) -> object:
        raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout)

    monkeypatch.setattr(team_router, "_run_tool", _raise_timeout)

    result = team_router.invoke_codex("hello", "/tmp/project", timeout=0)

    assert result == {"error": "codex-cli timeout", "fallback": "claude"}


def test_dispatch_to_model_preserves_agent_identity_for_security_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_registry = types.ModuleType("_agent_registry")
    setattr(fake_registry, "AGENT_REGISTRY", {
        "security-auditor": {
            "preferred_model": "codex-cli",
            "task_category": "deep",
            "skills": ["security-review"],
            "description": "Security specialist",
            "model_role": "slow",
        }
    })
    setattr(fake_registry, "detect_available_models", lambda: {
        "claude": True,
        "codex-cli": True,
        "gemini-cli": False,
    })
    monkeypatch.setitem(sys.modules, "_agent_registry", fake_registry)
    monkeypatch.setattr(
        team_router,
        "_invoke_provider",
        lambda provider_name, prompt, project_dir, timeout=120: {
            "provider": provider_name,
            "host_mode": "claude_dispatch",
            "error_code": "auth_required",
            "blocking_class": "authentication_required",
            "fallback_provider": "claude",
            "fallback_reason": "provider_login_required",
        },
    )

    result = team_router.dispatch_to_model("security-auditor", "audit auth flow", "/tmp/project")

    assert result["fallback_provider"] == "claude"
    assert result["fallback_mode"] == "provider_failover"
    assert result["fallback_agent_name"] == "security-auditor"
    assert result["fallback_model_tier"] == "opus"
    assert result["fallback_model_role"] == "slow"
    assert result["fallback_preserved_skills"] == ["security-review"]


def test_check_tool_auth_reports_unsupported_for_codex() -> None:
    ok, message = team_router._check_tool_auth("codex")

    assert ok is None
    assert message == "auth status check not supported"


def test_check_tool_auth_reports_unsupported_for_gemini() -> None:
    ok, message = team_router._check_tool_auth("gemini")

    assert ok is None
    assert message == "auth status check not supported"


def test_dispatch_params_include_model_version() -> None:
    registry_path = Path(__file__).resolve().parents[1] / "hooks" / "_agent_registry.py"
    spec = importlib.util.spec_from_file_location("agent_registry_for_team_router_tests", registry_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    params = module.get_dispatch_params("backend-engineer")
    assert "model_version" in params
    assert params["model_version"] == "gpt-5.3"


def test_invoke_codex_tmux_is_importable() -> None:
    assert hasattr(team_router, "invoke_codex_tmux")
    assert callable(team_router.invoke_codex_tmux)


def test_invoke_gemini_tmux_is_importable() -> None:
    assert hasattr(team_router, "invoke_gemini_tmux")
    assert callable(team_router.invoke_gemini_tmux)


def test_should_use_tmux_is_callable() -> None:
    result = team_router._should_use_tmux()
    assert isinstance(result, bool)


def test_should_use_tmux_false_for_dumb_term(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERM", "dumb")
    assert team_router._should_use_tmux() is False


def test_should_use_tmux_false_in_thread_pool() -> None:
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(team_router._should_use_tmux)
        result = future.result()
    assert result is False


def test_invoke_codex_tmux_falls_back_when_tmux_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(team_router, "_should_use_tmux", lambda: False)
    called: list[str] = []

    def mock_invoke_codex(prompt: str, project_dir: str, timeout: int = 120) -> dict[str, str]:
        called.append(prompt)
        return {"error": "codex-cli not found", "fallback": "claude"}

    monkeypatch.setattr(team_router, "invoke_codex", mock_invoke_codex)
    result = team_router.invoke_codex_tmux("test prompt", "/tmp")
    assert "fallback" in result or "output" in result or "error" in result
