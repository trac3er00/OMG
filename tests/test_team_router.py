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


def test_check_tool_auth_reports_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(args=["codex", "auth", "status"], returncode=0, stdout="logged in", stderr="")
    monkeypatch.setattr(team_router, "_run_tool", lambda _cmd, timeout=15: completed)

    ok, message = team_router._check_tool_auth("codex")

    assert ok is True
    assert message == "CLI is authenticated"


def test_check_tool_auth_reports_not_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(args=["gemini", "auth", "status"], returncode=1, stdout="", stderr="not logged in")
    monkeypatch.setattr(team_router, "_run_tool", lambda _cmd, timeout=15: completed)

    ok, message = team_router._check_tool_auth("gemini")

    assert ok is False
    assert "not authenticated" in message


def test_dispatch_params_include_model_version() -> None:
    registry_path = Path(__file__).resolve().parents[1] / "hooks" / "_agent_registry.py"
    spec = importlib.util.spec_from_file_location("agent_registry_for_team_router_tests", registry_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    params = module.get_dispatch_params("backend-engineer")
    assert "model_version" in params
    assert params["model_version"] == "gpt-5.3"
