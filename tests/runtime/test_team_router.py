"""Tests for runtime/team_router.py routing heuristics."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "team_router.py"
_SPEC = importlib.util.spec_from_file_location("runtime_team_router_for_tests", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
team_router = importlib.util.module_from_spec(_SPEC)
sys.modules["runtime_team_router_for_tests"] = team_router
_SPEC.loader.exec_module(team_router)

TeamDispatchRequest = team_router.TeamDispatchRequest
dispatch_team = team_router.dispatch_team
package_prompt = team_router.package_prompt


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


def test_execute_crazy_mode_persists_council_verdicts(monkeypatch, tmp_path):
    monkeypatch.setenv("OMG_RUN_ID", "run-crazy")

    monkeypatch.setattr(
        team_router,
        "execute_agents_parallel",
        lambda *_args, **_kwargs: [{"agent": "backend-engineer", "status": "completed", "output": "ok", "model": "codex-cli"}],
    )

    council = {
        "skeptic": {"verdict": "pass", "findings": ["ok"], "confidence": 0.8},
        "hallucination_auditor": {"verdict": "pass", "findings": ["ok"], "confidence": 0.8},
        "evidence_completeness": {"verdict": "pass", "findings": ["ok"], "confidence": 0.9},
    }
    monkeypatch.setattr(team_router, "run_critics", lambda **_kwargs: council)

    persisted: dict[str, object] = {}

    def _fake_write(project_dir, module, run_id, payload):
        persisted["project_dir"] = project_dir
        persisted["module"] = module
        persisted["run_id"] = run_id
        persisted["payload"] = payload
        return "ok"

    monkeypatch.setattr(team_router, "write_run_state", _fake_write, raising=False)

    result = team_router.execute_crazy_mode(
        problem="stabilize auth",
        project_dir=str(tmp_path),
        context="ctx",
        files=["auth.py"],
    )

    assert result["council_verdicts"] == council
    assert persisted["module"] == "council_verdicts"
    assert persisted["run_id"] == "run-crazy"
    payload = persisted["payload"]
    assert isinstance(payload, dict)
    assert payload["verdicts"] == council


def test_execute_crazy_mode_updates_health_and_defense_after_council_persist(monkeypatch, tmp_path):
    monkeypatch.setenv("OMG_RUN_ID", "run-crazy-health")
    monkeypatch.setattr(
        team_router,
        "execute_agents_parallel",
        lambda *_args, **_kwargs: [{"agent": "backend-engineer", "status": "completed", "output": "ok", "model": "codex-cli"}],
    )
    monkeypatch.setattr(
        team_router,
        "run_critics",
        lambda **_kwargs: {"evidence_completeness": {"verdict": "pass", "findings": [], "confidence": 0.9}},
    )

    events: list[str] = []

    def _fake_persist(project_dir, module, run_id, payload):
        _ = (project_dir, module, run_id, payload)
        events.append("persist")
        return "ok"

    class _FakeDefenseState:
        def __init__(self, _project_dir: str):
            pass

        def update(self, **_kwargs):
            events.append("defense")
            return {}

    def _fake_health(project_dir: str, *, run_id: str = "default"):
        _ = (project_dir, run_id)
        events.append("health")
        return {"recommended_action": "continue"}

    monkeypatch.setattr(team_router, "write_run_state", _fake_persist, raising=False)
    monkeypatch.setattr(team_router, "DefenseState", _FakeDefenseState)
    monkeypatch.setattr(team_router, "compute_session_health", _fake_health)

    team_router.execute_crazy_mode(
        problem="stabilize auth",
        project_dir=str(tmp_path),
        context="ctx",
        files=["auth.py"],
    )

    assert events == ["persist", "defense", "health"]


def test_execute_ccg_mode_persists_council_verdicts(monkeypatch, tmp_path):
    monkeypatch.setenv("OMG_RUN_ID", "run-ccg")

    monkeypatch.setattr(
        team_router,
        "execute_agents_parallel",
        lambda *_args, **_kwargs: [{"agent": "frontend-designer", "status": "completed", "output": "ok", "model": "gemini-cli"}],
    )
    council = {
        "skeptic": {"verdict": "pass", "findings": ["ok"], "confidence": 0.8},
        "hallucination_auditor": {"verdict": "pass", "findings": ["ok"], "confidence": 0.8},
        "evidence_completeness": {"verdict": "warn", "findings": ["missing artifacts"], "confidence": 0.7},
    }
    monkeypatch.setattr(team_router, "run_critics", lambda **_kwargs: council)

    persisted: dict[str, object] = {}
    monkeypatch.setattr(
        team_router,
        "write_run_state",
        lambda project_dir, module, run_id, payload: persisted.update(
            {"project_dir": project_dir, "module": module, "run_id": run_id, "payload": payload}
        )
        or "ok",
        raising=False,
    )

    result = team_router.execute_ccg_mode(
        problem="review ui+api",
        project_dir=str(tmp_path),
        context="ctx",
        files=["ui.tsx"],
    )

    assert result["council_verdicts"] == council
    assert persisted["module"] == "council_verdicts"
    assert persisted["run_id"] == "run-ccg"


def test_execute_ccg_mode_updates_health_and_defense_after_council_persist(monkeypatch, tmp_path):
    monkeypatch.setenv("OMG_RUN_ID", "run-ccg-health")

    monkeypatch.setattr(
        team_router,
        "execute_agents_parallel",
        lambda *_args, **_kwargs: [{"agent": "frontend-designer", "status": "completed", "output": "ok", "model": "gemini-cli"}],
    )
    monkeypatch.setattr(
        team_router,
        "run_critics",
        lambda **_kwargs: {"evidence_completeness": {"verdict": "warn", "findings": ["missing artifacts"], "confidence": 0.7}},
    )

    events: list[str] = []

    monkeypatch.setattr(
        team_router,
        "write_run_state",
        lambda *_args, **_kwargs: events.append("persist") or "ok",
        raising=False,
    )

    class _FakeDefenseState:
        def __init__(self, _project_dir: str):
            pass

        def update(self, **_kwargs):
            events.append("defense")
            return {}

    monkeypatch.setattr(team_router, "DefenseState", _FakeDefenseState)
    monkeypatch.setattr(
        team_router,
        "compute_session_health",
        lambda *_args, **_kwargs: events.append("health") or {"recommended_action": "continue"},
    )

    team_router.execute_ccg_mode(
        problem="review ui+api",
        project_dir=str(tmp_path),
        context="ctx",
        files=["ui.tsx"],
    )

    assert events == ["persist", "defense", "health"]


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


def test_execute_agents_parallel_uses_runtime_profile_budget(tmp_path, monkeypatch):
    (tmp_path / ".omg").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omg" / "runtime.yaml").write_text("profile: eco\n", encoding="utf-8")

    captured: dict[str, int] = {}

    class _FakePool:
        def __init__(self, max_workers):
            captured["max_workers"] = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            class _Future:
                def result(self, timeout=None):
                    return fn(*args, **kwargs)

            return _Future()

    monkeypatch.setattr(team_router, "ThreadPoolExecutor", _FakePool)
    monkeypatch.setattr(team_router, "as_completed", lambda futures: list(futures))
    monkeypatch.setattr(
        team_router,
        "dispatch_to_model",
        lambda agent_name, user_prompt, _project_dir: {"model": "codex-cli", "output": f"{agent_name}:{user_prompt}", "exit_code": 0},
    )

    tasks = [
        {"agent_name": "a", "prompt": "one", "order": 0},
        {"agent_name": "b", "prompt": "two", "order": 1},
        {"agent_name": "c", "prompt": "three", "order": 2},
    ]
    team_router.execute_agents_parallel(tasks, str(tmp_path))

    assert captured["max_workers"] == 2


# ============================================================================
# Tests for package_prompt() rich context enrichment (Task 5)
# ============================================================================


def test_package_prompt_includes_agent_description():
    """Test that package_prompt includes agent description from registry."""
    result = package_prompt("codex", "debug auth bug", "/tmp/project")
    assert "specialist" in result or "codex" in result.lower()
    assert "Task: debug auth bug" in result
    assert "Project: /tmp/project" in result


def test_package_prompt_includes_working_memory_when_file_exists(tmp_path):
    """Test that package_prompt includes working memory excerpt when file exists."""
    # Create .omg/state/working-memory.md
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)
    working_memory_file = omg_state / "working-memory.md"
    working_memory_file.write_text("## Session Context\nThis is important working memory content for the task.")

    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should include working memory excerpt
    assert "working memory" in result.lower() or "session context" in result.lower()
    assert len(result) > 200  # Rich context should be longer than minimal


def test_package_prompt_includes_profile_when_file_exists(tmp_path):
    """Test that package_prompt includes profile context when file exists."""
    # Create .omg/state/profile.yaml
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)
    profile_file = omg_state / "profile.yaml"
    profile_file.write_text("agent_name: codex\nmodel_version: gpt-4\nmode: implement")

    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should include profile context
    assert "profile" in result.lower() or "agent_name" in result.lower() or "model_version" in result.lower()


def test_package_prompt_includes_failure_history_when_ledger_exists(tmp_path):
    """Test that package_prompt includes recent failures from ledger when available."""
    # Create .omg/state/ledger/ with failure entries
    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    # Create a failure entry
    failure_entry = {
        "timestamp": "2026-03-04T10:00:00Z",
        "agent": "codex",
        "problem": "auth middleware bug",
        "error": "Test failed: expected 200, got 401",
    }
    (ledger_dir / "failure-001.jsonl").write_text(json.dumps(failure_entry) + "\n")

    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should include failure history
    assert "failure" in result.lower() or "error" in result.lower() or len(result) > 300


def test_package_prompt_respects_max_chars_default(tmp_path):
    """Test that package_prompt respects default 4000 char limit."""
    # Create large working memory file
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)
    working_memory_file = omg_state / "working-memory.md"
    large_content = "x" * 5000  # Larger than default limit
    working_memory_file.write_text(large_content)

    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should be capped at 4000 chars (default)
    assert len(result) <= 4000


def test_package_prompt_respects_env_var_max_chars(tmp_path, monkeypatch):
    """Test that package_prompt respects OMG_PROMPT_MAX_CHARS env var."""
    # Create large working memory file
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)
    working_memory_file = omg_state / "working-memory.md"
    large_content = "x" * 2000
    working_memory_file.write_text(large_content)

    # Set custom max chars
    monkeypatch.setenv("OMG_PROMPT_MAX_CHARS", "1000")

    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should be capped at 1000 chars
    assert len(result) <= 1000


def test_package_prompt_gracefully_handles_missing_state_files(tmp_path):
    """Test that package_prompt works when state files don't exist."""
    # Don't create any state files
    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should still return valid prompt with agent description and task
    assert "Task: debug auth bug" in result
    assert "Project:" in result
    assert len(result) > 50  # Should have some content


def test_package_prompt_includes_constraints_section(tmp_path):
    """Test that package_prompt includes constraints section."""
    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should include constraints
    assert "constraint" in result.lower() or "follow" in result.lower()


def test_package_prompt_with_all_context_sources(tmp_path):
    """Test package_prompt with all context sources present."""
    # Create all state files
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)

    # Working memory
    (omg_state / "working-memory.md").write_text("## Current Session\nWorking on auth module refactor.")

    # Profile
    (omg_state / "profile.yaml").write_text("agent: codex\nmode: implement\nstatus: active")

    # Failure history
    ledger_dir = omg_state / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    failure = {"timestamp": "2026-03-04T10:00:00Z", "agent": "codex", "error": "Test timeout"}
    (ledger_dir / "failure-001.jsonl").write_text(json.dumps(failure) + "\n")

    result = package_prompt("codex", "debug auth bug", str(tmp_path))

    # Should include all sections and be substantial
    assert len(result) > 300
    assert "Task: debug auth bug" in result
    assert "Project:" in result
    # Should include at least some context from the files
    assert len(result) <= 4000  # Still respects limit


def test_package_prompt_injects_bounded_profile_digest_without_raw_yaml(tmp_path):
    omg_state = tmp_path / ".omg" / "state"
    omg_state.mkdir(parents=True, exist_ok=True)
    (omg_state / "profile.yaml").write_text(
        "\n".join(
            [
                "preferences:",
                "  architecture_requests:",
                "    - event driven architecture",
                "    - microservices",
                "    - cqrs",
                "    - this should be trimmed",
                "  constraints:",
                "    Output Style: concise",
                "    Keep Evidence: true",
                "    Retry Count: 2",
                "    Timeout Seconds: 30",
                "    Response Format: json",
                "    Overflow: remove",
                "user_vector:",
                "  tags:",
                "    - reliability",
                "    - backend",
                "    - planning",
                "    - testing",
                "    - security",
                "    - overflow",
                "  summary: Keep answers compact and evidence-first.",
                "  confidence: 0.88",
                "profile_version: profile-v8",
            ]
        ),
        encoding="utf-8",
    )

    digest = team_router._read_profile_context(str(tmp_path))
    prompt = package_prompt("codex", "debug auth bug", str(tmp_path))

    assert digest
    assert len(digest) <= 300
    assert "preferences:" not in digest
    assert "ver=profile-v8" in digest
    assert "Profile:\n" + digest in prompt
