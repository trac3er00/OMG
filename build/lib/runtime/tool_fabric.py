from __future__ import annotations
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from registry.approval_artifact import (
    load_approval_artifact_from_path,
    verify_tool_approval,
)
from runtime.compliance_governor import evaluate_governed_tool_request
from runtime.release_run_coordinator import get_active_coordinator_run_id
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
    semantic_operations: tuple[str, ...]
    mutation_operations: tuple[str, ...]
    promotion_operations: tuple[str, ...]
    requires_signed_approval_for_mutation: bool
    requires_attestation_for_mutation: bool
    read_only_by_default: bool
    single_file_hash_bound: bool
    dry_run_first: bool
    require_run_scoped_evidence: bool
    require_fresh_evidence: bool
    evidence_max_age_seconds: int


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

        semantic_operations, mutation_operations, promotion_operations = self._parse_semantic_operations(
            fabric_obj=fabric_obj,
            default_tools=allowed_tools,
        )

        raw_max_age = fabric_obj.get("evidence_max_age_seconds")
        evidence_max_age_seconds = raw_max_age if isinstance(raw_max_age, int) and raw_max_age > 0 else 3600

        self._lanes[lane_key] = _LanePolicy(
            lane_name=lane_key,
            bundle_path=path,
            allowed_tools=allowed_tools,
            requires_signed_approval=bool(fabric_obj.get("requires_signed_approval", False)),
            requires_attestation=bool(fabric_obj.get("requires_attestation", False)),
            required_evidence=required_evidence,
            semantic_operations=semantic_operations,
            mutation_operations=mutation_operations,
            promotion_operations=promotion_operations,
            requires_signed_approval_for_mutation=bool(fabric_obj.get("requires_signed_approval_for_mutation", False)),
            requires_attestation_for_mutation=bool(fabric_obj.get("requires_attestation_for_mutation", False)),
            read_only_by_default=bool(fabric_obj.get("read_only_by_default", False)),
            single_file_hash_bound=bool(fabric_obj.get("single_file_hash_bound", False)),
            dry_run_first=bool(fabric_obj.get("dry_run_first", False)),
            require_run_scoped_evidence=bool(fabric_obj.get("require_run_scoped_evidence", False)),
            require_fresh_evidence=bool(fabric_obj.get("require_fresh_evidence", False)),
            evidence_max_age_seconds=evidence_max_age_seconds,
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

        operation = self._resolve_operation(lane, clean_tool, input_context)
        if operation is None:
            return ToolFabricResult(
                allowed=False,
                reason=f"semantic operation required for lane '{lane.lane_name}' tool '{clean_tool}'",
                evidence_path=None,
                ledger_entry=None,
            )

        mutation_capable = self._operation_is_mutation_capable(lane, operation, input_context)

        approval = self.check_approval(
            lane_name,
            clean_tool,
            clean_run_id,
            input_context,
            require_signed=(lane.requires_signed_approval or (mutation_capable and lane.requires_signed_approval_for_mutation)),
        )
        if not approval["allowed"]:
            return ToolFabricResult(False, str(approval["reason"]), None, None)

        if lane.single_file_hash_bound and mutation_capable:
            hash_gate = self._check_hash_edit_constraints(input_context)
            if not bool(hash_gate.get("allowed")):
                return ToolFabricResult(False, str(hash_gate.get("reason", "hash-edit constraints failed")), None, None)

        if mutation_capable and lane.requires_attestation_for_mutation:
            attestation_gate = self._check_mutation_attestation(
                context=input_context,
                lane_name=lane.lane_name,
                tool_name=clean_tool,
                run_id=clean_run_id,
                max_age_seconds=lane.evidence_max_age_seconds,
            )
            if not bool(attestation_gate.get("allowed")):
                return ToolFabricResult(False, str(attestation_gate.get("reason", "attestation required")), None, None)

        evidence = self.check_evidence(
            lane_name,
            clean_tool,
            clean_run_id,
            operation=operation,
            mutation_capable=mutation_capable,
        )
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
        require_signed: bool | None = None,
    ) -> dict[str, object]:
        lane = self._get_lane(lane_name)
        signed_required = lane.requires_signed_approval if require_signed is None else bool(require_signed)
        if not signed_required:
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

    def check_evidence(
        self,
        lane_name: str,
        tool_name: str,
        run_id: str,
        *,
        operation: str,
        mutation_capable: bool,
    ) -> dict[str, object]:
        lane = self._get_lane(lane_name)
        active_run_id = get_active_coordinator_run_id(self.project_dir)
        if active_run_id and active_run_id != run_id:
            return {
                "allowed": False,
                "reason": f"run_id mismatch with active coordinator run: active={active_run_id} requested={run_id}",
                "evidence_path": None,
            }

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
            if mutation_capable and lane.require_run_scoped_evidence:
                if "{run_id}" not in raw_path and run_id not in normalized:
                    return {
                        "allowed": False,
                        "reason": f"required evidence path must be run-scoped for mutation lane: {raw_path}",
                        "evidence_path": None,
                    }
            candidate = Path(normalized)
            if not candidate.is_absolute():
                candidate = Path(self.project_dir) / normalized
            if not candidate.exists():
                return {"allowed": False, "reason": f"required evidence missing: {normalized}", "evidence_path": None}
            payload_gate = self._validate_evidence_payload(
                candidate=candidate,
                lane=lane,
                lane_name=lane_name,
                tool_name=tool_name,
                operation=operation,
                run_id=run_id,
                mutation_capable=mutation_capable,
            )
            if not bool(payload_gate.get("allowed")):
                return {"allowed": False, "reason": str(payload_gate.get("reason", "invalid evidence")), "evidence_path": None}
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

    def _parse_semantic_operations(
        self,
        *,
        fabric_obj: dict[str, object],
        default_tools: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        raw_ops = fabric_obj.get("semantic_operations")
        if not isinstance(raw_ops, list):
            return tuple(), tuple(), tuple()

        op_names: list[str] = []
        mutation_ops: list[str] = []
        promotion_ops: list[str] = []
        for item in raw_ops:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            tool = str(item.get("tool", "")).strip()
            if not name or not tool:
                continue
            if tool not in default_tools:
                continue
            if name not in op_names:
                op_names.append(name)
            if bool(item.get("mutation_capable", False)) and name not in mutation_ops:
                mutation_ops.append(name)
            if bool(item.get("requires_explicit_promotion", False)) and name not in promotion_ops:
                promotion_ops.append(name)

        return tuple(op_names), tuple(mutation_ops), tuple(promotion_ops)

    def _resolve_operation(self, lane: _LanePolicy, tool_name: str, context: dict[str, object]) -> str | None:
        if not lane.semantic_operations:
            return ""
        raw_operation = str(context.get("operation", "")).strip()
        if raw_operation in lane.semantic_operations:
            return raw_operation
        if len(lane.semantic_operations) == 1:
            return lane.semantic_operations[0]
        if lane.read_only_by_default:
            for operation in lane.semantic_operations:
                if "read" in operation or "diagnostic" in operation:
                    return operation
        return None

    def _operation_is_mutation_capable(self, lane: _LanePolicy, operation: str, context: dict[str, object]) -> bool:
        if operation not in lane.mutation_operations:
            return False
        if lane.dry_run_first:
            dry_run = context.get("dry_run")
            if dry_run is None:
                dry_run = context.get("ast_dry_run")
            if dry_run is None:
                dry_run = True
            if bool(dry_run):
                return False
        if operation in lane.promotion_operations:
            promoted = self._is_truthy(context.get("promote_to_mutation")) or self._is_truthy(context.get("governed_promotion"))
            return bool(promoted)
        return True

    def _check_hash_edit_constraints(self, context: dict[str, object]) -> dict[str, object]:
        target_file = str(context.get("target_file", "")).strip()
        expected_hash = str(context.get("expected_hash", "")).strip()
        target_files_obj = context.get("target_files")
        if isinstance(target_files_obj, list):
            targets = [str(item).strip() for item in target_files_obj if str(item).strip()]
            if len(targets) != 1:
                return {"allowed": False, "reason": "hash-edit lane only allows single-file mutation"}
            if not target_file:
                target_file = targets[0]
        if not target_file:
            return {"allowed": False, "reason": "hash-edit lane requires target_file for single-file mutation"}
        if not expected_hash:
            return {"allowed": False, "reason": "hash-edit lane requires expected_hash binding"}
        return {"allowed": True, "reason": "hash-bound single-file constraints satisfied"}

    def _check_mutation_attestation(
        self,
        *,
        context: dict[str, object],
        lane_name: str,
        tool_name: str,
        run_id: str,
        max_age_seconds: int,
    ) -> dict[str, object]:
        attestation_obj = context.get("attestation_artifact")
        if not isinstance(attestation_obj, dict):
            return {
                "allowed": False,
                "reason": f"missing attestation artifact for lane={lane_name} tool={tool_name}",
            }
        attestation_run_id = str(attestation_obj.get("run_id", "")).strip()
        if attestation_run_id != run_id:
            return {"allowed": False, "reason": "attestation run_id mismatch"}
        attestation_lane = str(attestation_obj.get("lane", "")).strip()
        if attestation_lane and attestation_lane != lane_name:
            return {"allowed": False, "reason": "attestation lane mismatch"}
        attested_at = self._parse_timestamp(attestation_obj.get("attested_at"))
        if attested_at is None:
            return {"allowed": False, "reason": "attestation attested_at timestamp required"}
        max_age = timedelta(seconds=max(1, max_age_seconds))
        if datetime.now(timezone.utc) - attested_at > max_age:
            return {"allowed": False, "reason": "attestation artifact is stale"}
        return {"allowed": True, "reason": "attestation metadata verified"}

    def _validate_evidence_payload(
        self,
        *,
        candidate: Path,
        lane: _LanePolicy,
        lane_name: str,
        tool_name: str,
        operation: str,
        run_id: str,
        mutation_capable: bool,
    ) -> dict[str, object]:
        if not mutation_capable and not lane.require_fresh_evidence and not lane.require_run_scoped_evidence:
            return {"allowed": True, "reason": "evidence accepted"}
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            return {"allowed": False, "reason": f"evidence must be valid JSON: {candidate.name}"}
        if not isinstance(payload, dict):
            return {"allowed": False, "reason": f"evidence must be a JSON object: {candidate.name}"}

        evidence_run_id = str(payload.get("run_id", "")).strip()
        if lane.require_run_scoped_evidence and evidence_run_id != run_id:
            return {"allowed": False, "reason": "evidence run_id mismatch"}

        evidence_lane = str(payload.get("lane", "")).strip()
        if evidence_lane and evidence_lane != lane_name:
            return {"allowed": False, "reason": "evidence lane mismatch"}

        evidence_tool = str(payload.get("tool", "")).strip()
        if evidence_tool and evidence_tool != tool_name:
            return {"allowed": False, "reason": "evidence tool mismatch"}

        evidence_operation = str(payload.get("operation", "")).strip()
        if evidence_operation and operation and evidence_operation != operation:
            return {"allowed": False, "reason": "evidence operation mismatch"}

        if lane.require_fresh_evidence:
            generated_at = self._parse_timestamp(payload.get("generated_at"))
            if generated_at is None:
                return {"allowed": False, "reason": "evidence generated_at timestamp required"}
            max_age = timedelta(seconds=max(1, lane.evidence_max_age_seconds))
            if datetime.now(timezone.utc) - generated_at > max_age:
                return {"allowed": False, "reason": "evidence is stale"}
        return {"allowed": True, "reason": "evidence metadata verified"}

    def _parse_timestamp(self, raw: object) -> datetime | None:
        if not isinstance(raw, str) or not raw.strip():
            return None
        text = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_truthy(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "promote"}

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
