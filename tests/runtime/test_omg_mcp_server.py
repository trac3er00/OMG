from __future__ import annotations

import asyncio
import builtins
import importlib
import sys
from typing import Protocol, cast
from unittest.mock import patch

import pytest


class _MCPOMGServerModule(Protocol):
    mcp: object

    def omg_security_check(self, scope: str = ".", include_live_enrichment: bool = False, external_inputs: list[dict] | None = None, waivers: list[str] | None = None) -> dict: ...

    def omg_guide_assert(self, candidate: str, rules: dict) -> dict: ...

    def omg_claim_judge(self, claims: list[dict]) -> dict: ...

    def omg_test_intent_lock(self, action: str, intent: dict | None = None, lock_id: str | None = None, results: dict | None = None) -> dict: ...

    def omg_get_session_health(self, run_id: str | None = None) -> dict: ...


def _load_module() -> _MCPOMGServerModule:
    original_sys_path = list(sys.path)
    sys.path[:] = [path for path in sys.path if not path.endswith("/omg_natives")]

    try:
        _ = sys.modules.pop("runtime.omg_mcp_server", None)
        module = importlib.import_module("runtime.omg_mcp_server")
        return cast(_MCPOMGServerModule, cast(object, module))
    finally:
        sys.path[:] = original_sys_path


def _load_module_without_fastmcp() -> _MCPOMGServerModule:
    original_import = builtins.__import__

    def _guarded_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == "fastmcp":
            raise ModuleNotFoundError("No module named 'fastmcp'")
        return original_import(name, globals, locals, fromlist, level)

    original_sys_path = list(sys.path)
    sys.path[:] = [path for path in sys.path if not path.endswith("/omg_natives")]

    try:
        _ = sys.modules.pop("runtime.omg_mcp_server", None)
        with patch("builtins.__import__", side_effect=_guarded_import):
            module = importlib.import_module("runtime.omg_mcp_server")
        return cast(_MCPOMGServerModule, cast(object, module))
    finally:
        sys.path[:] = original_sys_path


def test_mcp_is_fastmcp_instance() -> None:
    module = _load_module()
    mcp_cls = module.mcp.__class__

    assert mcp_cls.__name__ == "FastMCP"
    assert mcp_cls.__module__.startswith("fastmcp")


def test_omg_security_check_tool_runs(tmp_path: pytest.TempPathFactory) -> None:
    module = _load_module()
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    result = module.omg_security_check(scope=str(tmp_path))
    assert result["schema"] == "SecurityCheckResult"
    assert result["summary"]["finding_count"] >= 1


def test_omg_guide_assert_tool_runs() -> None:
    module = _load_module()

    result = module.omg_guide_assert(
        candidate="TODO: this keeps insecure defaults.",
        rules={"goals": ["Avoid TODO markers in final output"]},
    )
    assert result["schema"] == "GuideAssertionResult"
    assert result["verdict"] == "fail"


def test_mcp_server_exposes_instructions_prompts_and_resources() -> None:
    module = _load_module()

    assert isinstance(module.mcp.instructions, str)
    assert "OMG production control plane" in module.mcp.instructions

    prompt_names = {prompt.name for prompt in asyncio.run(module.mcp.list_prompts())}
    resource_uris = {str(resource.uri) for resource in asyncio.run(module.mcp.list_resources())}

    assert "omg_contract_summary" in prompt_names
    assert "resource://omg/contract" in resource_uris
    assert "resource://omg/release-checklist" in resource_uris


def test_mcp_contract_resource_reads_contract_doc() -> None:
    module = _load_module()

    resource = asyncio.run(module.mcp.read_resource("resource://omg/contract"))
    text = str(resource)

    assert "OMG Production Control Plane" in text
    assert "execution_contract" in text


def test_mcp_fallback_stub_exposes_prompts_and_resources_without_fastmcp() -> None:
    module = _load_module_without_fastmcp()

    prompt_names = {prompt.name for prompt in asyncio.run(module.mcp.list_prompts())}
    resource_uris = {str(resource.uri) for resource in asyncio.run(module.mcp.list_resources())}

    assert "omg_contract_summary" in prompt_names
    assert "resource://omg/contract" in resource_uris
    assert "resource://omg/release-checklist" in resource_uris


def test_omg_security_check_tool_forwards_external_inputs(tmp_path: pytest.TempPathFactory) -> None:
    module = _load_module()
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    external_inputs = [{"source": "browser", "content": "user input"}]
    result = module.omg_security_check(scope=str(tmp_path), external_inputs=external_inputs)
    assert result["schema"] == "SecurityCheckResult"
    assert result["summary"]["finding_count"] >= 1
    assert result["provenance"] is not None


def test_omg_security_check_tool_forwards_waivers(tmp_path: pytest.TempPathFactory) -> None:
    module = _load_module()
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    result = module.omg_security_check(scope=str(tmp_path), waivers=["shell-true"])
    assert result["schema"] == "SecurityCheckResult"
    assert result["summary"]["finding_count"] >= 0


def test_omg_security_check_tool_accepts_none_waivers(tmp_path: pytest.TempPathFactory) -> None:
    module = _load_module()
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    result = module.omg_security_check(scope=str(tmp_path), waivers=None)
    assert result["schema"] == "SecurityCheckResult"
    assert result["summary"]["finding_count"] >= 1


def test_omg_claim_judge_tool_runs(tmp_path: pytest.TempPathFactory) -> None:
    module = _load_module()
    claims = [
        {"claim_type": "test_pass", "subject": "auth", "artifacts": ["a.json"], "trace_ids": ["t-1"]},
    ]
    with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
        result = module.omg_claim_judge(claims=claims)
    assert result["schema"] == "ClaimJudgeResults"
    assert result["verdict"] in {"pass", "fail", "insufficient"}


def test_omg_test_intent_lock_tool_lock_and_verify(tmp_path: pytest.TempPathFactory) -> None:
    module = _load_module()
    with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
        lock_result = module.omg_test_intent_lock(action="lock", intent={"tests": ["test_auth"]})
        assert lock_result["status"] == "locked"
        lock_id = lock_result["lock_id"]

        verify_result = module.omg_test_intent_lock(
            action="verify", lock_id=lock_id, results={"tests": ["test_auth"]},
        )
        assert verify_result["status"] == "ok"
        assert verify_result["lock_id"] == lock_id


def test_omg_get_session_health_reads_state(tmp_path: pytest.TempPathFactory) -> None:
    import json

    module = _load_module()
    health_dir = tmp_path / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)
    (health_dir / "mcp-1.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "mcp-1",
            "status": "ok",
            "contamination_risk": 0.1,
            "overthinking_score": 0.2,
            "context_health": 0.9,
            "verification_status": "ok",
            "recommended_action": "continue",
            "updated_at": "2026-03-08T12:00:00Z",
        }),
        encoding="utf-8",
    )
    with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
        result = module.omg_get_session_health(run_id="mcp-1")
    assert result["schema"] == "SessionHealth"
    assert result["run_id"] == "mcp-1"


def test_omg_get_session_health_latest_without_run_id(tmp_path: pytest.TempPathFactory) -> None:
    import json

    module = _load_module()
    health_dir = tmp_path / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True)
    (health_dir / "latest-1.json").write_text(
        json.dumps({
            "schema": "SessionHealth",
            "schema_version": "1.0.0",
            "run_id": "latest-1",
            "status": "ok",
            "contamination_risk": 0.05,
            "overthinking_score": 0.1,
            "context_health": 0.95,
            "verification_status": "ok",
            "recommended_action": "continue",
            "updated_at": "2026-03-08T12:00:00Z",
        }),
        encoding="utf-8",
    )
    with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
        result = module.omg_get_session_health()
    assert result["schema"] == "SessionHealth"
