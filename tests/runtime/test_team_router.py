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
            else:
                row["model"] = model
            out.append(row)
        return out

    monkeypatch.setattr(team_router, "execute_agents_sequentially", _fake_execute)

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
    assert result["model_mix"]["gpt"] == ["backend-engineer", "security-auditor"]
    assert result["model_mix"]["gemini"] == ["frontend-designer"]
    assert result["model_mix"]["claude"] == ["architect-mode", "testing-engineer"]
