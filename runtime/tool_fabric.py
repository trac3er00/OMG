from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from registry.approval_artifact import (
    load_approval_artifact_from_path,
    verify_tool_approval,
)
from runtime.compliance_governor import evaluate_governed_tool_request
from runtime.tool_plan_gate import has_tool_plan_for_run

try:
    import yaml
except Exception:
    yaml = None


_MODULE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ToolFabricResult:
    allowed: bool
    reason: str
    evidence_path: str | None
    ledger_entry: dict[str, object] | None


@dataclass(frozen=True)
class _LanePolicy:
    lane_name: str
    bundle_path: Path
    allowed_tools: tuple[str, ...]
    requires_signed_approval: bool
    requires_attestation: bool
    required_evidence: tuple[str, ...]


class ToolFabric:
    def __init__(self, project_dir: str | None = None) -> None:
        self.project_dir: str = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        self._lanes: dict[str, _LanePolicy] = {}

    def register_lane(self, lane_name: str, bundle_path: str) -> None:
        lane_key = str(lane_name).strip().lower()
        if not lane_key:
            raise ValueError("lane_name_required")
        if not bundle_path:
            raise ValueError("bundle_path_required")

        path = Path(bundle_path)
        if not path.is_absolute():
            candidate = Path(self.project_dir) / path
            if candidate.is_file():
                path = candidate
            else:
                path = _MODULE_DIR / path
        if not path.is_file():
            raise FileNotFoundError(f"bundle manifest not found: {path}")

        payload = self._load_bundle(path)
        fabric_obj = payload.get("tool_fabric")
        if not isinstance(fabric_obj, dict):
            raise ValueError(f"tool_fabric section missing from bundle: {path}")

        raw_tools = fabric_obj.get("tools")
        if isinstance(raw_tools, list):
            allowed_tools = tuple(str(item).strip() for item in raw_tools if str(item).strip())
        else:
            allowed_tools = self._fallback_allowed_tools(payload)

        raw_evidence = fabric_obj.get("required_evidence")
        required_evidence: tuple[str, ...]
        if isinstance(raw_evidence, list):
            required_evidence = tuple(str(item).strip() for item in raw_evidence if str(item).strip())
        else:
            required_evidence = tuple()

        self._lanes[lane_key] = _LanePolicy(
            lane_name=lane_key,
            bundle_path=path,
            allowed_tools=allowed_tools,
            requires_signed_approval=bool(fabric_obj.get("requires_signed_approval", False)),
            requires_attestation=bool(fabric_obj.get("requires_attestation", False)),
            required_evidence=required_evidence,
        )

    def request_tool(
        self,
        lane_name: str,
        tool_name: str,
        run_id: str,
        context: dict[str, object] | None,
    ) -> ToolFabricResult:
        lane = self._get_lane(lane_name)
        clean_tool = str(tool_name).strip()
        clean_run_id = str(run_id).strip()
        input_context = context if isinstance(context, dict) else {}

        if clean_tool not in lane.allowed_tools:
            return ToolFabricResult(
                allowed=False,
                reason=f"tool '{clean_tool}' is not declared for lane '{lane.lane_name}'",
                evidence_path=None,
                ledger_entry=None,
            )

        approval = self.check_approval(lane_name, clean_tool, clean_run_id, input_context)
        if not approval["allowed"]:
            return ToolFabricResult(False, str(approval["reason"]), None, None)

        evidence = self.check_evidence(lane_name, clean_tool, clean_run_id)
        if not evidence["allowed"]:
            return ToolFabricResult(False, str(evidence["reason"]), None, None)

        attestation_artifact_obj = input_context.get("attestation_artifact")
        attestation_artifact = cast(dict[str, object] | None, attestation_artifact_obj) if isinstance(attestation_artifact_obj, dict) else None
        clarification_status_obj = input_context.get("clarification_status")
        clarification_status = cast(dict[str, object] | None, clarification_status_obj) if isinstance(clarification_status_obj, dict) else None

        compliance = evaluate_governed_tool_request(
            project_dir=self.project_dir,
            run_id=clean_run_id,
            lane_name=lane.lane_name,
            tool=clean_tool,
            has_tool_plan=has_tool_plan_for_run(self.project_dir, clean_run_id),
            attestation_artifact=attestation_artifact,
            require_attestation=lane.requires_attestation,
            clarification_status=clarification_status,
        )
        if compliance.get("status") == "blocked":
            return ToolFabricResult(False, str(compliance.get("reason", "compliance blocked")), None, None)

        result_payload = self._execute_tool(input_context, lane.lane_name, clean_tool, clean_run_id)
        ledger_entry = self.record_execution(lane.lane_name, clean_tool, clean_run_id, result_payload)
        evidence_path = str(evidence.get("evidence_path") or "") or None
        return ToolFabricResult(True, "allowed", evidence_path, ledger_entry)

    def check_approval(
        self,
        lane_name: str,
        tool_name: str,
        run_id: str | None = None,
        context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        lane = self._get_lane(lane_name)
        if not lane.requires_signed_approval:
            return {"allowed": True, "reason": "approval not required"}
        if not run_id:
            return {"allowed": False, "reason": "run_id required for signed approval"}

        input_context = context if isinstance(context, dict) else {}
        approval_obj = input_context.get("approval_artifact")
        if isinstance(approval_obj, dict):
            verified = verify_tool_approval(
                approval_obj,
                lane_name=lane.lane_name,
                tool_name=tool_name,
                run_id=run_id,
            )
            if bool(verified.get("valid")):
                return {"allowed": True, "reason": "approval artifact verified"}

        approval_path = input_context.get("approval_artifact_path")
        if isinstance(approval_path, str) and approval_path.strip():
            loaded = load_approval_artifact_from_path(
                approval_path.strip(),
                expected_artifact_digest=self._tool_approval_digest(lane.lane_name, tool_name, run_id),
            )
            if bool(loaded.get("valid")):
                return {"allowed": True, "reason": "approval artifact path verified"}

        return {
            "allowed": False,
            "reason": f"signed approval required for lane={lane.lane_name} tool={tool_name}",
        }

    def check_evidence(self, lane_name: str, tool_name: str, run_id: str) -> dict[str, object]:
        _ = tool_name
        lane = self._get_lane(lane_name)
        if not lane.required_evidence:
            default_evidence = Path(self.project_dir) / ".omg" / "evidence" / f"{run_id}.json"
            if default_evidence.exists():
                return {
                    "allowed": True,
                    "reason": "default run evidence present",
                    "evidence_path": str(default_evidence.relative_to(self.project_dir)),
                }
            return {"allowed": True, "reason": "no explicit evidence requirements", "evidence_path": None}

        for raw_path in lane.required_evidence:
            normalized = raw_path.replace("{run_id}", run_id)
            candidate = Path(normalized)
            if not candidate.is_absolute():
                candidate = Path(self.project_dir) / normalized
            if not candidate.exists():
                return {"allowed": False, "reason": f"required evidence missing: {normalized}", "evidence_path": None}
            return {
                "allowed": True,
                "reason": "required evidence present",
                "evidence_path": str(candidate.relative_to(self.project_dir)),
            }

        return {"allowed": False, "reason": "required evidence missing", "evidence_path": None}

    def record_execution(
        self,
        lane_name: str,
        tool_name: str,
        run_id: str,
        result: dict[str, object],
    ) -> dict[str, object] | None:
        ledger_dir = Path(self.project_dir) / ".omg" / "state" / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = ledger_dir / "tool-ledger.jsonl"

        entry: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "lane": lane_name,
            "run_id": run_id,
            "source": "tool-fabric",
            "tool_fabric": {
                "lane": lane_name,
                "result": result,
            },
        }
        try:
            with ledger_path.open("a", encoding="utf-8") as handle:
                _ = handle.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=True) + "\n")
            return entry
        except Exception:
            return None

    def _execute_tool(
        self,
        context: dict[str, object],
        lane_name: str,
        tool_name: str,
        run_id: str,
    ) -> dict[str, object]:
        executor = context.get("executor")
        if callable(executor):
            output = executor(lane_name=lane_name, tool_name=tool_name, run_id=run_id, context=context)
            if isinstance(output, dict):
                return output
            return {"output": output}
        return {"status": "noop", "reason": "no executor bound in context"}

    def _get_lane(self, lane_name: str) -> _LanePolicy:
        lane_key = str(lane_name).strip().lower()
        if lane_key not in self._lanes:
            raise ValueError(f"lane not registered: {lane_key}")
        return self._lanes[lane_key]

    def _tool_approval_digest(self, lane_name: str, tool_name: str, run_id: str) -> str:
        from registry.approval_artifact import build_tool_approval_digest

        return build_tool_approval_digest(lane_name=lane_name, tool_name=tool_name, run_id=run_id)

    def _fallback_allowed_tools(self, payload: dict[str, object]) -> tuple[str, ...]:
        tool_policy = payload.get("tool_policy")
        if not isinstance(tool_policy, dict):
            return tuple()
        allowed_tools = tool_policy.get("allowed_tools")
        if not isinstance(allowed_tools, dict):
            return tuple()

        flattened: list[str] = []
        for value in allowed_tools.values():
            if not isinstance(value, list):
                continue
            for item in value:
                text = str(item).strip()
                if text and text not in flattened:
                    flattened.append(text)
        return tuple(flattened)

    def _load_bundle(self, path: Path) -> dict[str, object]:
        raw = path.read_text(encoding="utf-8")
        if yaml is not None:
            parsed = yaml.safe_load(raw)
            if parsed is None:
                return {}
            if isinstance(parsed, dict):
                return dict(parsed)
            raise ValueError(f"invalid bundle payload: {path}")
        parsed_json = json.loads(raw)
        if isinstance(parsed_json, dict):
            return dict(parsed_json)
        raise ValueError(f"invalid bundle payload: {path}")
