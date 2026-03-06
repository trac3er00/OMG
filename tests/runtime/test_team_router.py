"""Tests for runtime/team_router.py routing heuristics."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "team_router.py"
_SPEC = importlib.util.spec_from_file_location("runtime_team_router_for_tests", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
team_router = importlib.util.module_from_spec(_SPEC)
sys.modules["runtime_team_router_for_tests"] = team_router
_SPEC.loader.exec_module(team_router)

TeamDispatchRequest = team_router.TeamDispatchRequest
dispatch_team = team_router.dispatch_team


def _target(problem: str) -> str:
    out = dispatch_team(TeamDispatchRequest(target="auto", problem=problem)).to_dict()
    return out["evidence"]["target"]


def test_auto_route_respects_explicit_model_keywords():
    assert _target("please use gemini for this UI review") == "gemini"
    assert _target("please use codex for this backend debug") == "codex"
    assert _target("please use opencode for this implementation pass") == "opencode"
    assert _target("run a ccg review for this change") == "ccg"
    assert _target("ccg: review this change") == "ccg"
    assert _target("route both codex and gemini for this bug") == "ccg"


def test_auto_route_detects_full_stack_with_space_and_mixed_domain():
    assert _target("full stack login and dashboard review") == "ccg"
    assert _target("frontend and backend architecture pass") == "ccg"


def test_dispatch_team_reports_missing_cli_health(monkeypatch):
    monkeypatch.setattr(team_router, "_check_tool_available", lambda _name: False)
    result = dispatch_team(TeamDispatchRequest(target="codex", problem="debug auth bug")).to_dict()

    assert result["status"] == "ok"
    assert result["evidence"]["live_connection"] is False
    codex = result["evidence"]["cli_health"]["codex"]
    assert codex["available"] is False
    assert codex["live_connection"] is False


def test_dispatch_team_reports_live_connection_when_auth_ok(monkeypatch):
    monkeypatch.setattr(team_router, "_check_tool_available", lambda _name: True)
    monkeypatch.setattr(team_router, "_check_tool_auth", lambda _name: (True, "CLI is authenticated"))
    result = dispatch_team(TeamDispatchRequest(target="gemini", problem="review layout")).to_dict()

    assert result["status"] == "ok"
    assert result["evidence"]["live_connection"] is True
    gemini = result["evidence"]["cli_health"]["gemini"]
    assert gemini["available"] is True
    assert gemini["auth_ok"] is True
    assert gemini["live_connection"] is True


def test_dispatch_team_uses_provider_registry_for_codex_health(monkeypatch):
    class _FakeProvider:
        def detect(self) -> bool:
            return True

        def check_auth(self):
            return True, "auth probe succeeded"

    monkeypatch.setattr(
        team_router,
        "_get_registered_provider",
        lambda name: _FakeProvider() if name == "codex" else None,
        raising=False,
    )

    result = dispatch_team(TeamDispatchRequest(target="codex", problem="run implementation pass")).to_dict()

    assert result["evidence"]["target"] == "codex"
    assert result["evidence"]["live_connection"] is True
    codex = result["evidence"]["cli_health"]["codex"]
    assert codex["available"] is True
    assert codex["auth_ok"] is True
    assert codex["status_message"] == "auth probe succeeded"


def test_dispatch_team_uses_provider_registry_for_opencode_health(monkeypatch):
    class _FakeProvider:
        def detect(self) -> bool:
            return True

        def check_auth(self):
            return True, "auth probe succeeded"

    monkeypatch.setattr(
        team_router,
        "_get_registered_provider",
        lambda name: _FakeProvider() if name == "opencode" else None,
        raising=False,
    )

    result = dispatch_team(TeamDispatchRequest(target="opencode", problem="run implementation pass")).to_dict()

    assert result["evidence"]["target"] == "opencode"
    assert result["evidence"]["live_connection"] is True
    opencode = result["evidence"]["cli_health"]["opencode"]
    assert opencode["available"] is True
    assert opencode["auth_ok"] is True
    assert opencode["status_message"] == "auth probe succeeded"


def test_dispatch_team_represents_kimi_target(monkeypatch):
    class _FakeProvider:
        def detect(self) -> bool:
            return True

        def check_auth(self):
            return None, "auth status check not supported"

    monkeypatch.setattr(
        team_router,
        "_get_registered_provider",
        lambda name: _FakeProvider() if name == "kimi" else None,
        raising=False,
    )

    result = dispatch_team(TeamDispatchRequest(target="kimi", problem="review local workspace")).to_dict()

    assert result["evidence"]["target"] == "kimi"
    kimi = result["evidence"]["cli_health"]["kimi"]
    assert kimi["available"] is True
    assert kimi["auth_ok"] is None
    assert kimi["status_message"] == "auth status check not supported"


def test_normalize_provider_error_marks_service_disabled_as_non_retryable():
    result = team_router._normalize_provider_error(
        "gemini",
        {
            "stderr": "This service has been disabled in this account for violation of Terms of Service.",
            "exit_code": 1,
        },
    )

    assert result["error_code"] == "service_disabled"
    assert result["blocking_class"] == "service_disabled"
    assert result["retryable"] is False
    assert result["recovery_action"] == "appeal_provider_account"
    assert result["fallback_provider"] == "claude"
    assert result["fallback_reason"] == "provider_service_disabled"
    assert result["fallback_mode"] == "provider_failover"
    assert result["fallback_trigger_class"] == "hard_failure"


def test_normalize_provider_error_surfaces_codex_feature_warning_separately():
    result = team_router._normalize_provider_error(
        "codex",
        {
            "stderr": (
                "WARN codex_core::features: unknown feature key in config: rmcp_client\n"
                "ERROR rmcp::transport::worker: worker quit with fatal: "
                "Transport channel closed, when Auth(TokenRefreshFailed(\"Failed to parse server response\"))\n"
            ),
            "exit_code": 0,
        },
    )

    assert result["error_code"] == "auth_required"
    assert result["blocking_class"] == "authentication_required"
    assert result["recovery_action"] == "login_to_provider"
    assert result["warning_codes"] == ["unsupported_feature_flag"]
    assert "rmcp_client" in result["warning_messages"][0]
    assert result["additional_recovery_actions"] == ["remove_incompatible_feature_flags"]
    assert result["fallback_mode"] == "provider_failover"
    assert result["fallback_trigger_class"] == "hard_failure"


def test_normalize_provider_error_marks_timeout_as_retry_exhausted_claude_failover():
    result = team_router._normalize_provider_error(
        "codex",
        {
            "error": "codex-cli timeout",
            "exit_code": 124,
        },
    )

    assert result["error_code"] == "provider_error"
    assert result["fallback_provider"] == "claude"
    assert result["fallback_mode"] == "provider_failover"
    assert result["fallback_trigger_class"] == "retry_exhausted"


def test_normalize_provider_error_does_not_failover_when_success_has_only_warning():
    result = team_router._normalize_provider_error(
        "codex",
        {
            "model": "codex-cli",
            "output": "OK",
            "stderr": "WARN codex_core::shell_snapshot: cleanup skipped",
            "exit_code": 0,
        },
    )

    assert result["blocking_class"] == "ready"
    assert result["fallback_provider"] == ""
    assert result["fallback_reason"] == ""
    assert result["fallback_mode"] == ""
    assert result["fallback_trigger_class"] == ""


def test_invoke_provider_ensures_mcp_dependency_before_dispatch(monkeypatch):
    calls: list[str] = []

    class _FakeProvider:
        def invoke(self, prompt: str, project_dir: str, timeout: int = 120):
            return {"model": "codex-cli", "output": "OK", "exit_code": 0}

        def invoke_tmux(self, prompt: str, project_dir: str, timeout: int = 120):
            return {"model": "codex-cli", "output": "OK", "exit_code": 0}

    monkeypatch.setattr(team_router, "_get_registered_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(team_router, "_should_use_tmux", lambda: False)
    monkeypatch.setattr(team_router, "ensure_memory_server", lambda: calls.append("ensure") or {"status": "started", "url": "http://127.0.0.1:8765/mcp"})
    monkeypatch.setattr(
        team_router,
        "check_memory_server",
        lambda: {"running": True, "url": "http://127.0.0.1:8765/mcp", "pid": 1, "health_ok": True},
    )

    result = team_router._invoke_provider("codex", "Reply with OK.", "/tmp/project")

    assert calls == ["ensure"]
    assert result["dependency_state"] == "ready"
    assert result["mcp_server"]["running"] is True
    assert result["blocking_class"] == "ready"


def test_host_execution_matrix_is_exposed():
    matrix = team_router.get_host_execution_matrix()

    assert "claude_native" in matrix
    assert "claude_dispatch" in matrix


def test_execute_crazy_mode_launches_five_workers(monkeypatch):
    captured: list[dict[str, object]] = []

    def _fake_execute(agent_tasks, _project_dir, timeout_per_agent=120):
        captured.extend(agent_tasks)
        out = []
        for task in agent_tasks:
            name = task.get("agent_name", "")
            model = "codex-cli" if name in {"backend-engineer", "security-auditor"} else "gemini-cli" if name == "frontend-designer" else "claude"
            row = {
                "agent": name,
                "status": "completed",
                "output": f"ok:{name}",
            }
            if model == "claude":
                row["fallback"] = "claude"
                row["fallback_provider"] = "claude"
                row["fallback_mode"] = "provider_failover"
                row["fallback_model_tier"] = "sonnet"
            else:
                row["model"] = model
            out.append(row)
        return out

    monkeypatch.setattr(team_router, "execute_agents_parallel", _fake_execute)

    result = team_router.execute_crazy_mode(
        problem="stabilize auth and ui",
        project_dir="/tmp/project",
        context="session context",
        files=["auth.py", "ui.tsx"],
    )

    assert len(captured) == 5
    names = [str(task.get("agent_name")) for task in captured]
    assert names == [
        "architect-mode",
        "backend-engineer",
        "frontend-designer",
        "security-auditor",
        "testing-engineer",
    ]
    assert result["worker_count"] == 5
    assert result["target_worker_count"] == 5
    assert result["parallel_execution"] is True
    assert result["sequential_execution"] is False
    assert result["model_mix"]["gpt"] == ["backend-engineer", "security-auditor"]
    assert result["model_mix"]["gemini"] == ["frontend-designer"]
    assert result["model_mix"]["claude"] == ["architect-mode", "testing-engineer"]
    assert result["model_mix"]["claude_tiers"] == {
        "haiku": [],
        "sonnet": ["architect-mode", "testing-engineer"],
        "opus": [],
    }


def test_execute_agents_parallel_preserves_all_results_when_orders_collide(monkeypatch):
    def _fake_dispatch(agent_name: str, user_prompt: str, _project_dir: str):
        return {
            "model": "codex-cli",
            "output": f"{agent_name}:{user_prompt}",
            "exit_code": 0,
        }

    monkeypatch.setattr(team_router, "dispatch_to_model", _fake_dispatch)

    tasks = [
        {"agent_name": "a", "prompt": "one", "order": 0},
        {"agent_name": "b", "prompt": "two", "order": 0},
        {"agent_name": "c", "prompt": "three", "order": 0},
    ]
    results = team_router.execute_agents_parallel(tasks, "/tmp/project")

    assert len(results) == 3
    assert [row["agent"] for row in results] == ["a", "b", "c"]
    assert [row["output"] for row in results] == ["a:one", "b:two", "c:three"]


def test_execute_agents_parallel_marks_only_failed_agent_as_claude_failover(monkeypatch):
    def _fake_dispatch(agent_name: str, user_prompt: str, _project_dir: str):
        if agent_name == "frontend-designer":
            return {
                "error": "service disabled",
                "fallback": "claude",
                "fallback_provider": "claude",
                "fallback_mode": "provider_failover",
                "fallback_trigger_class": "hard_failure",
                "fallback_model_tier": "sonnet",
                "fallback_model_role": "default",
                "fallback_agent_name": agent_name,
                "fallback_preserved_skills": ["frontend-design"],
            }
        return {
            "model": "codex-cli",
            "output": f"{agent_name}:{user_prompt}",
            "exit_code": 0,
        }

    monkeypatch.setattr(team_router, "dispatch_to_model", _fake_dispatch)

    tasks = [
        {"agent_name": "backend-engineer", "prompt": "one", "order": 0},
        {"agent_name": "frontend-designer", "prompt": "two", "order": 1},
    ]
    results = team_router.execute_agents_parallel(tasks, "/tmp/project")

    assert results[0]["agent"] == "backend-engineer"
    assert results[0]["status"] == "completed"
    assert results[0]["model"] == "codex-cli"
    assert results[1]["agent"] == "frontend-designer"
    assert results[1]["status"] == "fallback-claude"
    assert results[1]["fallback_provider"] == "claude"
    assert results[1]["fallback_model_tier"] == "sonnet"
    assert results[1]["fallback_agent_name"] == "frontend-designer"
