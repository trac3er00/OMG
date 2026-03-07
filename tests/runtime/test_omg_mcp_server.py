from __future__ import annotations

import importlib
import sys
from typing import Protocol, cast

import pytest


class _MCPOMGServerModule(Protocol):
    mcp: object

    def omg_security_check(self, scope: str = ".", include_live_enrichment: bool = False) -> dict: ...

    def omg_guide_assert(self, candidate: str, rules: dict) -> dict: ...


def _load_module() -> _MCPOMGServerModule:
    original_sys_path = list(sys.path)
    sys.path[:] = [path for path in sys.path if not path.endswith("/omg_natives")]

    try:
        _ = sys.modules.pop("runtime.omg_mcp_server", None)
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

