from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from runtime.tool_plan_gate import build_tool_plan, tool_plan_gate_check
import runtime.tool_plan_gate as tool_plan_gate


def test_build_tool_plan_returns_required_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_RUN_ID", "run-shape")

    plan = build_tool_plan(
        "need docs and one security scan",
        available_tools=["context7", "omg_security_check"],
    )

    assert plan["plan_id"]
    assert plan["goal"] == "need docs and one security scan"
    assert isinstance(plan["budget_estimate"], dict)
    assert isinstance(plan["tools"], list)
    assert plan["tools"]


def test_build_tool_plan_args_are_non_empty_dicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_RUN_ID", "run-args")

    plan = build_tool_plan(
        "need docs and one security scan",
        available_tools=["context7", "omg_security_check"],
    )

    tools = cast(list[dict[str, object]], plan["tools"])
    for tool in tools:
        assert "name" in tool
        assert "rationale" in tool
        args = cast(dict[str, object], tool.get("args", {}))
        assert len(args) >= 1


def test_build_tool_plan_matches_goal_to_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_RUN_ID", "run-match")

    plan = build_tool_plan(
        "need docs and one security scan",
        available_tools=["context7", "omg_security_check", "websearch"],
    )

    selected = {str(tool.get("name", "")) for tool in cast(list[dict[str, object]], plan["tools"])}
    assert "context7" in selected
    assert "omg_security_check" in selected
    assert "websearch" not in selected


def test_build_tool_plan_persists_plan_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_RUN_ID", "run-persist")

    plan = build_tool_plan("security scan", available_tools=["omg_security_check"])

    output = tmp_path / ".omg" / "state" / "tool_plans" / f"{plan['plan_id']}.json"
    assert output.exists()

    text = output.read_text(encoding="utf-8")
    assert f'"plan_id": "{plan["plan_id"]}"' in text
    assert '"run_id": "run-persist"' in text
    assert '"tools": [' in text


def test_tool_plan_gate_blocks_when_council_evidence_fails(tmp_path: Path) -> None:
    run_id = "run-council-block"
    plans_dir = tmp_path / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{run_id}-plan-test.json").write_text("{}", encoding="utf-8")

    council_dir = tmp_path / ".omg" / "state" / "council_verdicts"
    council_dir.mkdir(parents=True, exist_ok=True)
    (council_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "schema": "CouncilVerdicts",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "status": "blocked",
                "verification_status": "blocked",
                "updated_at": "2026-03-08T00:00:00Z",
                "verdicts": {
                    "evidence_completeness": {
                        "verdict": "fail",
                        "findings": ["missing evidence artifacts"],
                        "confidence": 0.95,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = tool_plan_gate_check(str(tmp_path), run_id, "Write")

    assert result["status"] == "blocked"
    assert "council" in str(result["reason"]).lower()


def test_build_tool_plan_uses_bounded_context_packet_for_optimization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("OMG_RUN_ID", "run-opt")

    captured: dict[str, object] = {}

    class _FakeEngine:
        def __init__(self, project_dir: str) -> None:
            captured["project_dir"] = project_dir

        def build_packet(self, run_id: str, *, delta_only: bool = False) -> dict[str, object]:
            captured["run_id"] = run_id
            captured["delta_only"] = delta_only
            return {
                "summary": "pressure high",
                "artifact_pointers": [".omg/state/context_engine_packet.json"],
                "budget": {"max_chars": 1000, "used_chars": 980},
                "delta_only": True,
                "run_id": run_id,
            }

    monkeypatch.setattr(tool_plan_gate, "ContextEngine", _FakeEngine, raising=False)

    plan = build_tool_plan(
        "need docs and latest research",
        available_tools=["context7", "websearch", "omg_security_check"],
        context_packet={"summary": "caller context"},
        run_id="run-opt",
    )
    plan_obj = cast(dict[str, object], plan)
    context_packet_obj = cast(dict[str, object], plan_obj["context_packet"])
    budget_obj = cast(dict[str, object], context_packet_obj["budget"])

    assert captured["project_dir"] == str(tmp_path)
    assert captured["run_id"] == "run-opt"
    assert captured["delta_only"] is True
    assert budget_obj["used_chars"] == 980
