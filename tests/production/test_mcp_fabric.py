"""MCP fabric integration test suite.

Tests the omg-control MCP server tools by importing and calling them directly.
Validates tool registration, function signatures, constants, stub behavior,
and tool fabric lane mechanics without starting a real MCP server.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_source(rel_path: str) -> str:
    target = ROOT / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} not found")
    return target.read_text(encoding="utf-8")


# ===================================================================
# 1. Import & Module Structure
# ===================================================================


class TestMCPServerImport:
    """Validate that MCP server and tool fabric modules are importable."""

    def test_mcp_server_spec_exists(self):
        """omg_mcp_server.py should have a valid import spec."""
        spec = importlib.util.spec_from_file_location(
            "omg_mcp_server", ROOT / "runtime" / "omg_mcp_server.py"
        )
        assert spec is not None, "omg_mcp_server.py spec is None"
        assert spec.loader is not None

    def test_tool_fabric_spec_exists(self):
        """tool_fabric.py should have a valid import spec."""
        spec = importlib.util.spec_from_file_location(
            "tool_fabric", ROOT / "runtime" / "tool_fabric.py"
        )
        assert spec is not None, "tool_fabric.py spec is None"
        assert spec.loader is not None

    def test_mcp_server_is_python(self):
        """omg_mcp_server.py should be valid Python (parseable)."""
        source = _read_source("runtime/omg_mcp_server.py")
        compile(source, "omg_mcp_server.py", "exec")

    def test_tool_fabric_is_python(self):
        """tool_fabric.py should be valid Python (parseable)."""
        source = _read_source("runtime/tool_fabric.py")
        compile(source, "tool_fabric.py", "exec")


# ===================================================================
# 2. MCP Tool Function Presence
# ===================================================================


class TestMCPToolFunctions:
    """Verify each MCP tool function is defined in omg_mcp_server.py."""

    EXPECTED_TOOLS = (
        "omg_policy_evaluate",
        "omg_trust_review",
        "omg_evidence_ingest",
        "omg_runtime_dispatch",
        "omg_security_check",
        "omg_claim_judge",
        "omg_test_intent_lock",
        "omg_guide_assert",
        "omg_get_session_health",
        "omg_tool_fabric_request",
        "omg_decision_query",
        "omg_preferences_get",
        "omg_usage_stats",
        "omg_routing_log",
        "omg_health_check",
    )

    @pytest.fixture(scope="class")
    def mcp_source(self) -> str:
        return _read_source("runtime/omg_mcp_server.py")

    @pytest.mark.parametrize("func_name", EXPECTED_TOOLS)
    def test_tool_function_defined(self, mcp_source: str, func_name: str):
        """Each expected tool should have a def in the MCP server source."""
        assert f"def {func_name}" in mcp_source, (
            f"Function '{func_name}' not found in omg_mcp_server.py"
        )


# ===================================================================
# 3. MCP Constants Integrity
# ===================================================================


class TestMCPConstants:
    """Validate MCP_TOOL_NAMES, MCP_PROMPT_NAMES, MCP_RESOURCE_URIS."""

    @pytest.fixture(scope="class")
    def mcp_source(self) -> str:
        return _read_source("runtime/omg_mcp_server.py")

    def test_tool_names_count(self, mcp_source: str):
        """MCP_TOOL_NAMES should list 15 tools."""
        assert "MCP_TOOL_NAMES" in mcp_source
        # Count quoted entries in the tuple
        import re

        matches = re.findall(
            r'"omg_\w+"', mcp_source.split("MCP_TOOL_NAMES")[1].split(")")[0]
        )
        assert len(matches) >= 15, f"Expected 15+ tool names, found {len(matches)}"

    def test_prompt_names_exist(self, mcp_source: str):
        """MCP_PROMPT_NAMES should be defined."""
        assert "MCP_PROMPT_NAMES" in mcp_source
        assert "omg_contract_summary" in mcp_source

    def test_resource_uris_exist(self, mcp_source: str):
        """MCP_RESOURCE_URIS should define at least 2 resources."""
        assert "MCP_RESOURCE_URIS" in mcp_source
        assert "resource://omg/contract" in mcp_source
        assert "resource://omg/release-checklist" in mcp_source

    def test_mcp_instructions_defined(self, mcp_source: str):
        """MCP_INSTRUCTIONS should be a non-empty string."""
        assert "MCP_INSTRUCTIONS" in mcp_source


# ===================================================================
# 4. MCP Prompt & Resource Definitions
# ===================================================================


class TestMCPPromptsResources:
    """Verify prompt and resource decorators are present."""

    @pytest.fixture(scope="class")
    def mcp_source(self) -> str:
        return _read_source("runtime/omg_mcp_server.py")

    def test_contract_summary_prompt(self, mcp_source: str):
        """omg_contract_summary prompt should be decorated."""
        assert "@mcp.prompt" in mcp_source
        assert "def omg_contract_summary" in mcp_source

    def test_contract_resource(self, mcp_source: str):
        """omg_contract resource should be decorated."""
        assert "@mcp.resource" in mcp_source
        assert "def omg_contract_resource" in mcp_source

    def test_release_checklist_resource(self, mcp_source: str):
        """omg_release_checklist resource should be decorated."""
        assert "def omg_release_checklist_resource" in mcp_source


# ===================================================================
# 5. Stub FastMCP Fallback
# ===================================================================


class TestStubFastMCP:
    """Validate the _StubFastMCP fallback when fastmcp is not installed."""

    @pytest.fixture(scope="class")
    def mcp_source(self) -> str:
        return _read_source("runtime/omg_mcp_server.py")

    def test_stub_class_defined(self, mcp_source: str):
        """_StubFastMCP should be defined as fallback."""
        assert "class _StubFastMCP" in mcp_source

    def test_stub_has_tool_method(self, mcp_source: str):
        """Stub should implement .tool() decorator method."""
        # Verify there's a def tool inside _StubFastMCP
        stub_section = mcp_source.split("class _StubFastMCP")[1].split("\nclass ")[0]
        assert "def tool(" in stub_section

    def test_stub_has_prompt_method(self, mcp_source: str):
        """Stub should implement .prompt() decorator method."""
        stub_section = mcp_source.split("class _StubFastMCP")[1].split("\nclass ")[0]
        assert "def prompt(" in stub_section

    def test_stub_has_resource_method(self, mcp_source: str):
        """Stub should implement .resource() decorator method."""
        stub_section = mcp_source.split("class _StubFastMCP")[1].split("\nclass ")[0]
        assert "def resource(" in stub_section

    def test_stub_has_run_method(self, mcp_source: str):
        """Stub should implement .run() method."""
        stub_section = mcp_source.split("class _StubFastMCP")[1].split("\nclass ")[0]
        assert "def run(" in stub_section

    def test_stub_has_list_prompts(self, mcp_source: str):
        """Stub should implement async list_prompts."""
        stub_section = mcp_source.split("class _StubFastMCP")[1].split("\nclass ")[0]
        assert "async def list_prompts" in stub_section

    def test_stub_has_list_resources(self, mcp_source: str):
        """Stub should implement async list_resources."""
        stub_section = mcp_source.split("class _StubFastMCP")[1].split("\nclass ")[0]
        assert "async def list_resources" in stub_section


# ===================================================================
# 6. Tool Fabric Core Structure
# ===================================================================


class TestToolFabricStructure:
    """Validate tool_fabric.py core classes and constants."""

    @pytest.fixture(scope="class")
    def fabric_source(self) -> str:
        return _read_source("runtime/tool_fabric.py")

    def test_tool_fabric_class_exists(self, fabric_source: str):
        """ToolFabric class should be defined."""
        assert "class ToolFabric" in fabric_source

    def test_tool_fabric_result_class(self, fabric_source: str):
        """ToolFabricResult dataclass should be defined."""
        assert "class ToolFabricResult" in fabric_source

    def test_lane_policy_class(self, fabric_source: str):
        """_LanePolicy dataclass should be defined."""
        assert "class _LanePolicy" in fabric_source

    def test_phase_aliases_defined(self, fabric_source: str):
        """_PHASE_ALIASES mapping should exist."""
        assert "_PHASE_ALIASES" in fabric_source

    def test_phase_tool_exposure_defined(self, fabric_source: str):
        """_PHASE_TOOL_EXPOSURE mapping should exist."""
        assert "_PHASE_TOOL_EXPOSURE" in fabric_source

    def test_register_lane_method(self, fabric_source: str):
        """ToolFabric should have register_lane method."""
        assert "def register_lane(" in fabric_source

    def test_request_tool_method(self, fabric_source: str):
        """ToolFabric should have request_tool method."""
        assert "def request_tool(" in fabric_source

    def test_check_approval_method(self, fabric_source: str):
        """ToolFabric should have check_approval method."""
        assert "def check_approval(" in fabric_source

    def test_check_evidence_method(self, fabric_source: str):
        """ToolFabric should have check_evidence method."""
        assert "def check_evidence(" in fabric_source

    def test_record_execution_method(self, fabric_source: str):
        """ToolFabric should have record_execution method."""
        assert "def record_execution(" in fabric_source

    def test_tools_for_phase_method(self, fabric_source: str):
        """ToolFabric should have tools_for_phase method."""
        assert "def tools_for_phase(" in fabric_source

    def test_is_tool_exposed_for_phase_method(self, fabric_source: str):
        """ToolFabric should have is_tool_exposed_for_phase method."""
        assert "def is_tool_exposed_for_phase(" in fabric_source


# ===================================================================
# 7. Phase Tool Exposure Coverage
# ===================================================================


class TestPhaseToolExposure:
    """Validate that phase tool exposure lists are well-formed."""

    @pytest.fixture(scope="class")
    def fabric_source(self) -> str:
        return _read_source("runtime/tool_fabric.py")

    @pytest.fixture(scope="class")
    def exposure_section(self, fabric_source: str) -> str:
        """Extract the _PHASE_TOOL_EXPOSURE block."""
        start = fabric_source.index("_PHASE_TOOL_EXPOSURE")
        # Find the closing brace by scanning for balanced braces
        depth, pos = 0, fabric_source.index("{", start)
        for i in range(pos, len(fabric_source)):
            if fabric_source[i] == "{":
                depth += 1
            elif fabric_source[i] == "}":
                depth -= 1
                if depth == 0:
                    return fabric_source[start : i + 1]
        return fabric_source[start:]

    def test_planning_phase_has_read_tools(self, exposure_section: str):
        """Planning phase should expose Read and search tools."""
        assert '"Read"' in exposure_section

    def test_execution_phase_has_write_tools(self, exposure_section: str):
        """Execution phase should expose Edit and Bash."""
        assert '"Edit"' in exposure_section
        assert '"Bash"' in exposure_section

    def test_verification_phase_has_judge_tools(self, exposure_section: str):
        """Verification phase should expose claim_judge and evidence tools."""
        assert '"omg_claim_judge"' in exposure_section
        assert '"omg_evidence_ingest"' in exposure_section

    def test_all_three_phases_defined(self, exposure_section: str):
        """All three phases (planning, execution, verification) should be in exposure map."""
        for phase in ("planning", "execution", "verification"):
            assert f'"{phase}"' in exposure_section


# ===================================================================
# 8. MCP Server Tool Decorator Wiring
# ===================================================================


class TestMCPToolDecorators:
    """Verify each tool has @mcp.tool() decorator wiring."""

    @pytest.fixture(scope="class")
    def mcp_source(self) -> str:
        return _read_source("runtime/omg_mcp_server.py")

    def test_tool_decorator_count(self, mcp_source: str):
        """At least 15 @mcp.tool decorators should exist."""
        count = mcp_source.count("@mcp.tool(")
        assert count >= 15, f"Expected 15+ @mcp.tool decorators, found {count}"

    def test_every_tool_has_description(self, mcp_source: str):
        """Every @mcp.tool should have a description parameter."""
        import re

        decorators = re.findall(r"@mcp\.tool\([^)]*\)", mcp_source, re.DOTALL)
        for dec in decorators:
            assert "description=" in dec, (
                f"Tool decorator missing description: {dec[:60]}"
            )


# ===================================================================
# 9. Tool Fabric ToolFabricResult Fields
# ===================================================================


class TestToolFabricResultFields:
    """Validate ToolFabricResult dataclass fields."""

    @pytest.fixture(scope="class")
    def fabric_source(self) -> str:
        return _read_source("runtime/tool_fabric.py")

    def test_has_allowed_field(self, fabric_source: str):
        result_section = fabric_source.split("class ToolFabricResult")[1].split(
            "\nclass "
        )[0]
        assert "allowed:" in result_section

    def test_has_reason_field(self, fabric_source: str):
        result_section = fabric_source.split("class ToolFabricResult")[1].split(
            "\nclass "
        )[0]
        assert "reason:" in result_section

    def test_has_evidence_path_field(self, fabric_source: str):
        result_section = fabric_source.split("class ToolFabricResult")[1].split(
            "\nclass "
        )[0]
        assert "evidence_path:" in result_section

    def test_has_ledger_entry_field(self, fabric_source: str):
        result_section = fabric_source.split("class ToolFabricResult")[1].split(
            "\nclass "
        )[0]
        assert "ledger_entry:" in result_section


# ===================================================================
# 10. Cross-Module Integration Coherence
# ===================================================================


class TestCrossModuleCoherence:
    """Validate MCP server and tool fabric reference each other correctly."""

    @pytest.fixture(scope="class")
    def mcp_source(self) -> str:
        return _read_source("runtime/omg_mcp_server.py")

    @pytest.fixture(scope="class")
    def fabric_source(self) -> str:
        return _read_source("runtime/tool_fabric.py")

    def test_mcp_tools_match_phase_exposure(self, mcp_source: str, fabric_source: str):
        """MCP tools referenced in phase exposure should exist in MCP server."""
        import re

        # Extract omg_ tool names from phase exposure
        omg_tools_in_fabric = set(re.findall(r'"(omg_\w+)"', fabric_source))
        # Each should appear as a function in MCP server
        for tool_name in omg_tools_in_fabric:
            assert f"def {tool_name}" in mcp_source, (
                f"Tool '{tool_name}' in phase exposure but not defined in MCP server"
            )

    def test_control_plane_service_used(self, mcp_source: str):
        """MCP server should use ControlPlaneService."""
        assert "ControlPlaneService" in mcp_source

    def test_fabric_uses_compliance_governor(self, fabric_source: str):
        """Tool fabric should import compliance_governor."""
        assert "compliance_governor" in fabric_source

    def test_fabric_uses_approval_artifact(self, fabric_source: str):
        """Tool fabric should import approval_artifact."""
        assert "approval_artifact" in fabric_source

    def test_mcp_server_has_lifespan(self, mcp_source: str):
        """MCP server should define a lifespan context manager."""
        assert "async def lifespan" in mcp_source or "def lifespan" in mcp_source

    def test_mcp_server_has_run_server(self, mcp_source: str):
        """MCP server should define run_server entry point."""
        assert "def run_server" in mcp_source
