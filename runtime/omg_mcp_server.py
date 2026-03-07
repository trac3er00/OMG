from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.asset_loader import resolve_asset

_mcp_import_error: ModuleNotFoundError | None = None
_FastMCP: Any

try:
    from fastmcp import FastMCP as _ImportedFastMCP
    _FastMCP = _ImportedFastMCP
except ModuleNotFoundError as exc:
    _mcp_import_error = exc

    def _passthrough_decorator(*_args: Any, **_kwargs: Any):
        def decorator(func: Any) -> Any:
            return func

        return decorator

    @dataclass
    class _StubPrompt:
        name: str
        description: str
        handler: Any

    @dataclass
    class _StubResource:
        uri: str
        name: str
        description: str
        mime_type: str
        handler: Any

    class _StubFastMCP:  # type: ignore[override]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._import_error = _mcp_import_error
            self.instructions = str(_kwargs.get("instructions", ""))
            self._prompts: list[_StubPrompt] = []
            self._resources: dict[str, _StubResource] = {}

        def tool(self, *_args: Any, **_kwargs: Any):
            return _passthrough_decorator(*_args, **_kwargs)

        def prompt(self, *, name: str, description: str = ""):
            def decorator(func: Any) -> Any:
                self._prompts.append(_StubPrompt(name=name, description=description, handler=func))
                return func

            return decorator

        def resource(
            self,
            uri: str,
            *,
            name: str = "",
            description: str = "",
            mime_type: str = "text/plain",
        ):
            def decorator(func: Any) -> Any:
                self._resources[uri] = _StubResource(
                    uri=uri,
                    name=name,
                    description=description,
                    mime_type=mime_type,
                    handler=func,
                )
                return func

            return decorator

        async def list_prompts(self) -> list[_StubPrompt]:
            return list(self._prompts)

        async def list_resources(self) -> list[_StubResource]:
            return list(self._resources.values())

        async def read_resource(self, uri: str) -> Any:
            resource = self._resources[str(uri)]
            return resource.handler()

        def run(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("fastmcp is required to run the OMG MCP server") from self._import_error

    _StubFastMCP.__module__ = "fastmcp"
    _FastMCP = _StubFastMCP

FastMCP = _FastMCP

from control_plane.service import ControlPlaneService


MCP_INSTRUCTIONS = (
    "OMG production control plane MCP. Prefer omg-control prompts and resources for "
    "contract, release-readiness, and governance context before using direct tools."
)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_: object) -> AsyncIterator[None]:
    yield


mcp = FastMCP("OMG Control MCP", lifespan=lifespan, instructions=MCP_INSTRUCTIONS)


def _service() -> ControlPlaneService:
    return ControlPlaneService(project_dir=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))


def _read_repo_text(rel_path: str) -> str:
    return resolve_asset(rel_path).read_text(encoding="utf-8")


@mcp.tool()
def omg_policy_evaluate(tool: str, input: dict[str, Any]) -> dict[str, Any]:
    _status, payload = _service().policy_evaluate({"tool": tool, "input": input})
    return payload


@mcp.tool()
def omg_trust_review(file_path: str, old_config: dict[str, Any], new_config: dict[str, Any]) -> dict[str, Any]:
    _status, payload = _service().trust_review({"file_path": file_path, "old_config": old_config, "new_config": new_config})
    return payload


@mcp.tool()
def omg_evidence_ingest(
    run_id: str,
    tests: list[dict[str, Any]],
    security_scans: list[dict[str, Any]],
    diff_summary: dict[str, Any],
    reproducibility: dict[str, Any],
    unresolved_risks: list[str],
    provenance: list[dict[str, Any]] | None = None,
    trust_scores: dict[str, Any] | None = None,
    api_twin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _status, payload = _service().evidence_ingest(
        {
            "run_id": run_id,
            "tests": tests,
            "security_scans": security_scans,
            "diff_summary": diff_summary,
            "reproducibility": reproducibility,
            "unresolved_risks": unresolved_risks,
            "provenance": provenance or [],
            "trust_scores": trust_scores or {},
            "api_twin": api_twin or {},
        }
    )
    return payload


@mcp.tool()
def omg_runtime_dispatch(runtime: str, idea: dict[str, Any]) -> dict[str, Any]:
    _status, payload = _service().runtime_dispatch({"runtime": runtime, "idea": idea})
    return payload


@mcp.tool()
def omg_security_check(scope: str = ".", include_live_enrichment: bool = False, external_inputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    _status, payload = _service().security_check({"scope": scope, "include_live_enrichment": include_live_enrichment, "external_inputs": external_inputs})
    return payload


@mcp.tool()
def omg_guide_assert(candidate: str, rules: dict[str, Any]) -> dict[str, Any]:
    _status, payload = _service().guide_assert({"candidate": candidate, "rules": rules})
    return payload


@mcp.prompt(name="omg_contract_summary", description="Summarize the OMG production contract and generated host outputs")
def omg_contract_summary(channel: str = "public") -> str:
    return (
        "Summarize the OMG production control plane contract for channel "
        f"`{channel}`. Include execution_contract, host_compilation_rules, "
        "MCP resources, prompts, and release-readiness expectations."
    )


@mcp.resource("resource://omg/contract", name="omg_contract", description="Canonical OMG production contract document", mime_type="text/markdown")
def omg_contract_resource() -> str:
    return _read_repo_text("OMG_COMPAT_CONTRACT.md")


@mcp.resource(
    "resource://omg/release-checklist",
    name="omg_release_checklist",
    description="Public release checklist for OMG",
    mime_type="text/markdown",
)
def omg_release_checklist_resource() -> str:
    return _read_repo_text("docs/release-checklist.md")


def run_server() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
