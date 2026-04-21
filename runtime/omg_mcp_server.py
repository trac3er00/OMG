from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.asset_loader import resolve_asset
from runtime.adoption import CANONICAL_VERSION
from runtime.compliance_governor import classify_bash_command_mode
from runtime.evidence_narrator import BLOCK_REASON_CATALOG
from runtime.profile_io import ensure_governed_preferences, load_profile
from runtime.tool_plan_gate import resolve_current_run_id, tool_plan_gate_check

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
                self._prompts.append(
                    _StubPrompt(name=name, description=description, handler=func)
                )
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
            while True:
                time.sleep(1)

    _StubFastMCP.__module__ = "fastmcp"
    _FastMCP = _StubFastMCP

FastMCP = _FastMCP

from control_plane.service import ControlPlaneService


MCP_INSTRUCTIONS = (
    "OMG production control plane MCP. Prefer omg-control prompts and resources for "
    "contract, release-readiness, and governance context before using direct tools."
)

MCP_TOOL_NAMES: tuple[str, ...] = (
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

MCP_PROMPT_NAMES: tuple[str, ...] = ("omg_contract_summary",)
MCP_RESOURCE_URIS: tuple[str, ...] = (
    "resource://omg/contract",
    "resource://omg/release-checklist",
)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_: object) -> AsyncIterator[None]:
    yield


mcp = FastMCP("OMG Control MCP", lifespan=lifespan, instructions=MCP_INSTRUCTIONS)


def _service() -> ControlPlaneService:
    return ControlPlaneService(
        project_dir=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    )


def _project_dir() -> str:
    return _service().project_dir


def _read_repo_text(rel_path: str) -> str:
    return resolve_asset(rel_path).read_text(encoding="utf-8")


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            records.append(loaded)
    return records


def _profile_path(project_dir: str) -> Path:
    return Path(project_dir) / ".omg" / "state" / "profile.yaml"


def _routing_log_path(project_dir: str) -> Path:
    return Path(project_dir) / ".omg" / "state" / "ledger" / "routing-decisions.jsonl"


def _decision_log_path(project_dir: str) -> Path:
    return Path(project_dir) / ".omg" / "state" / "ledger" / "decisions.jsonl"


def _lookup_nested_value(payload: dict[str, Any], dotted_field: str) -> Any:
    current: Any = payload
    for part in dotted_field.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _enrich_blocked_response(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "blocked":
        return result
    reason = str(result.get("reason", ""))
    narrative = BLOCK_REASON_CATALOG.get(reason)
    if narrative:
        return {
            **result,
            "summary": narrative.get("summary", reason),
            "explanation": narrative.get("explanation", ""),
            "next_actions": narrative.get("next_actions", []),
        }
    return result


@mcp.tool(
    description="Evaluate whether a proposed tool call is allowed under OMG policy and mutation gates. Use before running Write/Edit/Bash operations to catch blocked actions with structured reasons and remediation guidance."
)
def omg_policy_evaluate(tool: str, input: dict[str, Any]) -> dict[str, Any]:
    if tool in {"Write", "Edit", "MultiEdit", "Bash"}:
        run_id_candidate = input.get("run_id") if isinstance(input, dict) else None
        run_id: str | None = None
        if isinstance(run_id_candidate, str) and run_id_candidate.strip():
            run_id = run_id_candidate.strip()
        metadata = input.get("metadata") if isinstance(input, dict) else None
        if not run_id and isinstance(metadata, dict):
            metadata_run_id = metadata.get("run_id")
            if isinstance(metadata_run_id, str) and metadata_run_id.strip():
                run_id = metadata_run_id.strip()
        if not run_id:
            run_id = resolve_current_run_id()

        should_gate_tool_plan = tool in {"Write", "Edit", "MultiEdit"}
        if tool == "Bash":
            bash_mode = (
                classify_bash_command_mode(str(input.get("command", "")))
                if isinstance(input, dict)
                else "read"
            )
            should_gate_tool_plan = bash_mode in {"mutation", "external"}

        if should_gate_tool_plan:
            tool_plan_result = tool_plan_gate_check(
                _service().project_dir, run_id, tool, tool_input=input
            )
            if tool_plan_result.get("status") == "blocked":
                return _enrich_blocked_response(tool_plan_result)

        lock_id: str | None = None
        if isinstance(metadata, dict):
            lock_id_candidate = metadata.get("lock_id")
            if isinstance(lock_id_candidate, str):
                lock_id = lock_id_candidate
        direct_lock_id = input.get("lock_id") if isinstance(input, dict) else None
        if isinstance(direct_lock_id, str) and direct_lock_id.strip():
            lock_id = direct_lock_id

        exemption = input.get("exemption") if isinstance(input, dict) else None
        gate_status, gate_payload = _service().mutation_gate_check(
            {
                "tool": tool,
                "file_path": str(input.get("file_path", ""))
                if isinstance(input, dict)
                else "",
                "lock_id": lock_id,
                "exemption": exemption,
                "command": str(input.get("command", ""))
                if isinstance(input, dict)
                else "",
                "run_id": run_id,
                "metadata": metadata if isinstance(metadata, dict) else None,
            }
        )
        if gate_status == 200 and gate_payload.get("status") == "blocked":
            return _enrich_blocked_response(gate_payload)

    _status, payload = _service().policy_evaluate({"tool": tool, "input": input})
    return _enrich_blocked_response(payload)


@mcp.tool(
    description="Review a configuration change for trust and safety regressions by comparing old and new config objects. Use when editing settings, CI policy, or host integration files to surface high-risk drift."
)
def omg_trust_review(
    file_path: str, old_config: dict[str, Any], new_config: dict[str, Any]
) -> dict[str, Any]:
    _status, payload = _service().trust_review(
        {"file_path": file_path, "old_config": old_config, "new_config": new_config}
    )
    return payload


@mcp.tool(
    description="Ingest run evidence (tests, security scans, reproducibility, unresolved risks) into a signed evidence pack. Call this after execution or verification so claim-judge and release checks have machine-readable proof."
)
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


@mcp.tool(
    description="Route a task idea to a target runtime adapter and return normalized dispatch metadata. Use when an agent must select or validate the execution runtime before launching governed work."
)
def omg_runtime_dispatch(runtime: str, idea: dict[str, Any]) -> dict[str, Any]:
    _status, payload = _service().runtime_dispatch({"runtime": runtime, "idea": idea})
    return payload


@mcp.tool(
    description="Run OMG security auditing for a project scope with optional live enrichment and waiver input. Use during verification to detect secrets, risky patterns, and policy violations before completion claims."
)
def omg_security_check(
    scope: str = ".",
    include_live_enrichment: bool = False,
    external_inputs: list[dict[str, Any]] | None = None,
    waivers: list[str] | None = None,
) -> dict[str, Any]:
    _status, payload = _service().security_check(
        {
            "scope": scope,
            "include_live_enrichment": include_live_enrichment,
            "external_inputs": external_inputs,
            "waivers": waivers,
        }
    )
    return payload


@mcp.tool(
    description="Judge structured completion claims against available evidence and return pass/fail verdicts with reasons. Use as the final quality gate before reporting success or preparing release readiness outputs."
)
def omg_claim_judge(claims: list[dict[str, Any]]) -> dict[str, Any]:
    _status, payload = _service().claim_judge({"claims": claims})
    return payload


@mcp.tool(
    description="Create or verify a test-intent lock that prevents silent weakening of tests. Use action=create before risky edits and action=verify after tests run to ensure expected intent and delta constraints hold."
)
def omg_test_intent_lock(
    action: str,
    intent: dict[str, Any] | None = None,
    lock_id: str | None = None,
    results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _status, payload = _service().test_intent_lock(
        {"action": action, "intent": intent, "lock_id": lock_id, "results": results}
    )
    return payload


@mcp.tool(
    description="Assert that generated text or config snippets conform to required guide rules. Use when prompts, policies, or generated artifacts must satisfy deterministic formatting and guardrail constraints."
)
def omg_guide_assert(candidate: str, rules: dict[str, Any]) -> dict[str, Any]:
    _status, payload = _service().guide_assert({"candidate": candidate, "rules": rules})
    return payload


@mcp.tool(
    description="Fetch session health for a specific run or the latest run snapshot. Use in planning and verification to confirm whether the session is in a safe state before continuing mutations or finalizing output."
)
def omg_get_session_health(run_id: str | None = None) -> dict[str, Any]:
    _status, payload = _service().session_health({"run_id": run_id})
    return payload


@mcp.tool(
    description="Request governed execution of a tool through a registered fabric lane with approval and evidence checks. Use for high-risk operations that require lane policy enforcement and immutable ledger records."
)
def omg_tool_fabric_request(
    lane_name: str,
    tool_name: str,
    run_id: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _status, payload = _service().tool_fabric_request(
        {
            "lane_name": lane_name,
            "tool_name": tool_name,
            "run_id": run_id,
            "context": context or {},
        }
    )
    return payload


@mcp.tool(
    description="Query the decision ledger by type, keyword, and recency to inspect prior runtime decisions."
)
def omg_decision_query(
    decision_type: str | None = None,
    keyword: str | None = None,
    since_days: int | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    try:
        DecisionLedger = __import__(
            "runtime.decision_ledger", fromlist=["DecisionLedger"]
        ).DecisionLedger

        results = DecisionLedger(project_dir=_project_dir()).query(
            decision_type=decision_type,
            keyword=keyword,
            since_days=since_days,
            limit=limit,
        )
        return {
            "decisions": [decision.to_dict() for decision in results],
            "count": len(results),
            "filters": {
                "decision_type": decision_type,
                "keyword": keyword,
                "since_days": since_days,
                "limit": limit,
            },
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "decisions": [],
            "count": 0,
            "filters": {
                "decision_type": decision_type,
                "keyword": keyword,
                "since_days": since_days,
                "limit": limit,
            },
        }


@mcp.tool(
    description="Get a stored user preference from the OMG profile, including governed preferences and direct profile fields."
)
def omg_preferences_get(
    field: str | None = None,
    section: str | None = None,
) -> dict[str, Any]:
    project_dir = _project_dir()
    profile = load_profile(str(_profile_path(project_dir)))
    ensure_governed_preferences(profile)

    governed_obj = profile.get("governed_preferences")
    governed = governed_obj if isinstance(governed_obj, dict) else {}
    sections = [section] if section else ["style", "safety"]
    matches: list[dict[str, Any]] = []

    for section_name in sections:
        raw_entries = governed.get(section_name, [])
        entries = raw_entries if isinstance(raw_entries, list) else []
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            if field is not None and str(raw_entry.get("field", "")).strip() != field:
                continue
            matches.append(dict(raw_entry))

    direct_value = None
    if field:
        direct_value = _lookup_nested_value(profile, field)
        if direct_value is None:
            preferences_obj = profile.get("preferences")
            preferences = preferences_obj if isinstance(preferences_obj, dict) else {}
            direct_value = _lookup_nested_value(preferences, field)

    resolved_value = matches[-1].get("value") if matches else direct_value
    return {
        "field": field,
        "section": section,
        "preferences": matches,
        "value": resolved_value,
        "found": bool(matches) or direct_value is not None,
        "count": len(matches),
    }


@mcp.tool(
    description="Return local MCP session usage statistics including registered surfaces and ledger counts."
)
def omg_usage_stats() -> dict[str, Any]:
    project_dir = _project_dir()
    decisions = _read_jsonl_records(_decision_log_path(project_dir))
    routing_entries = _read_jsonl_records(_routing_log_path(project_dir))
    return {
        "session_id": "current",
        "status": "running",
        "version": CANONICAL_VERSION,
        "project_dir": project_dir,
        "tools_registered": len(MCP_TOOL_NAMES),
        "prompts_registered": len(MCP_PROMPT_NAMES),
        "resources_registered": len(MCP_RESOURCE_URIS),
        "decision_count": len(decisions),
        "routing_decision_count": len(routing_entries),
        "fastmcp_available": _mcp_import_error is None,
    }


@mcp.tool(
    description="Read the persisted model routing decision log for the current project session."
)
def omg_routing_log(limit: int = 20) -> dict[str, Any]:
    entries = _read_jsonl_records(_routing_log_path(_project_dir()))
    safe_limit = max(0, limit)
    return {
        "entries": entries[-safe_limit:] if safe_limit else [],
        "count": min(len(entries), safe_limit),
        "total": len(entries),
    }


@mcp.tool(
    description="Return OMG MCP server health, version, and registered capability counts."
)
def omg_health_check() -> dict[str, Any]:
    return {
        "status": "healthy",
        "version": CANONICAL_VERSION,
        "project_dir": _project_dir(),
        "tools_registered": len(MCP_TOOL_NAMES),
        "prompts_registered": len(MCP_PROMPT_NAMES),
        "resources_registered": len(MCP_RESOURCE_URIS),
        "fastmcp_available": _mcp_import_error is None,
        "modules": [
            "decision_ledger",
            "profile_io",
            "session_health",
            "model_router",
        ],
    }


@mcp.prompt(
    name="omg_contract_summary",
    description="Summarize the OMG production contract and generated host outputs",
)
def omg_contract_summary(channel: str = "public") -> str:
    return (
        "Summarize the OMG production control plane contract for channel "
        f"`{channel}`. Include execution_contract, host_compilation_rules, "
        "MCP resources, prompts, and release-readiness expectations."
    )


@mcp.resource(
    "resource://omg/contract",
    name="omg_contract",
    description="Canonical OMG production contract document",
    mime_type="text/markdown",
)
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
