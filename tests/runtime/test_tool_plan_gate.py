from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from runtime.tool_plan_gate import build_tool_plan


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
