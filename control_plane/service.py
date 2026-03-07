"""Control plane service handlers for OMG v1."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from hooks.policy_engine import (
    evaluate_bash_command,
    evaluate_file_access,
    evaluate_supply_artifact,
)
from hooks.security_validators import validate_opaque_identifier
from hooks.shadow_manager import create_evidence_pack
from hooks.trust_review import review_config_change
from lab.pipeline import run_pipeline
from registry.verify_artifact import verify_artifact
from runtime.guide_assert import guide_assert
from runtime.dispatcher import dispatch_runtime
from runtime.security_check import run_security_check


class ControlPlaneService:
    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    def policy_evaluate(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        tool = str(payload.get("tool", ""))
        input_data = payload.get("input", {})

        if tool == "Bash":
            command = str((input_data or {}).get("command", ""))
            decision = evaluate_bash_command(command)
            return 200, decision.to_dict()

        if tool in {"Read", "Write", "Edit", "MultiEdit"}:
            file_path = str((input_data or {}).get("file_path", ""))
            decision = evaluate_file_access(tool, file_path)
            return 200, decision.to_dict()

        if tool == "SupplyArtifact":
            artifact = payload.get("artifact", {})
            mode = str(payload.get("mode", "warn_and_run"))
            decision = evaluate_supply_artifact(artifact, mode=mode)
            return 200, decision.to_dict()

        return 400, {
            "status": "error",
            "error_code": "INVALID_POLICY_INPUT",
            "message": "Unsupported tool for policy evaluation",
        }

    def trust_review(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        file_path = str(payload.get("file_path", "settings.json"))
        old_config = payload.get("old_config", {})
        new_config = payload.get("new_config", {})
        if not isinstance(old_config, dict) or not isinstance(new_config, dict):
            return 400, {
                "status": "error",
                "error_code": "INVALID_TRUST_INPUT",
                "message": "old_config and new_config must be objects",
            }
        review = review_config_change(file_path, old_config, new_config)
        return 200, review

    def evidence_ingest(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        run_id = str(payload.get("run_id", "")).strip()
        required = ["tests", "security_scans", "diff_summary", "reproducibility", "unresolved_risks"]
        missing = [key for key in required if key not in payload]

        if not run_id:
            return 400, {
                "status": "error",
                "error_code": "INVALID_EVIDENCE_INPUT",
                "message": "run_id is required",
            }
        try:
            run_id = validate_opaque_identifier(run_id, "run_id")
        except ValueError as exc:
            return 400, {
                "status": "error",
                "error_code": "INVALID_EVIDENCE_INPUT",
                "message": str(exc),
            }
        if missing:
            return 400, {
                "status": "error",
                "error_code": "INVALID_EVIDENCE_INPUT",
                "message": f"Missing required fields: {', '.join(missing)}",
            }

        path = create_evidence_pack(
            self.project_dir,
            run_id,
            tests=payload.get("tests"),
            security_scans=payload.get("security_scans"),
            diff_summary=payload.get("diff_summary"),
            reproducibility=payload.get("reproducibility"),
            unresolved_risks=payload.get("unresolved_risks"),
            provenance=payload.get("provenance"),
            trust_scores=payload.get("trust_scores"),
            api_twin=payload.get("api_twin"),
        )
        return 202, {
            "status": "accepted",
            "run_id": run_id,
            "evidence_path": os.path.relpath(path, self.project_dir),
        }

    def security_check(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        scope = str(payload.get("scope", "."))
        include_live_enrichment = bool(payload.get("include_live_enrichment", False))
        result = run_security_check(
            project_dir=self.project_dir,
            scope=scope,
            include_live_enrichment=include_live_enrichment,
        )
        return 200, result

    def guide_assert(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        candidate = str(payload.get("candidate", ""))
        rules = payload.get("rules", {})
        if not isinstance(rules, dict):
            return 400, {
                "status": "error",
                "error_code": "INVALID_GUIDE_INPUT",
                "message": "rules must be an object",
            }
        return 200, guide_assert(candidate, rules)

    def runtime_dispatch(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        runtime = str(payload.get("runtime", "")).strip()
        idea = payload.get("idea", {})
        if not runtime:
            return 400, {
                "status": "error",
                "error_code": "INVALID_RUNTIME_INPUT",
                "message": "runtime is required",
            }
        if not isinstance(idea, dict):
            return 400, {
                "status": "error",
                "error_code": "INVALID_RUNTIME_INPUT",
                "message": "idea must be an object",
            }
        result = dispatch_runtime(runtime, idea)
        if result.get("status") == "error":
            return 400, result
        return 200, result

    def registry_verify(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        artifact = payload.get("artifact", {})
        mode = str(payload.get("mode", "warn_and_run"))
        if not isinstance(artifact, dict):
            return 400, {
                "status": "error",
                "error_code": "INVALID_REGISTRY_INPUT",
                "message": "artifact must be an object",
            }
        decision = verify_artifact(artifact, mode=mode)
        return 200, decision

    def lab_jobs(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            return 400, {
                "status": "error",
                "error_code": "INVALID_LAB_INPUT",
                "message": "job payload must be an object",
            }
        result = run_pipeline(payload)
        return 201 if result.get("status") in {"ready", "failed_evaluation"} else 400, result

    def scoreboard_baseline(self) -> tuple[int, dict[str, Any]]:
        return 200, {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline": {
                "safe_autonomy_rate": 0.0,
                "pr_throughput": 0.0,
                "adoption_velocity": 0.0,
            },
            "target_policy": "non-regression-or-better",
        }
