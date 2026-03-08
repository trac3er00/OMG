"""Control plane service handlers for OMG v1."""
# pyright: reportImportCycles=false
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
from runtime.claim_judge import judge_claims
from runtime.mutation_gate import check_mutation_allowed
from runtime.security_check import run_security_check
from runtime.test_intent_lock import lock_intent, verify_intent


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
            route_metadata=payload.get("route_metadata"),
            trace_ids=payload.get("trace_ids"),
            lineage=payload.get("lineage"),
            claims=payload.get("claims"),
            test_delta=payload.get("test_delta"),
            browser_evidence_path=payload.get("browser_evidence_path"),
            repro_pack_path=payload.get("repro_pack_path"),
        )
        return 202, {
            "status": "accepted",
            "run_id": run_id,
            "evidence_path": os.path.relpath(path, self.project_dir),
        }

    def security_check(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        scope = str(payload.get("scope", "."))
        include_live_enrichment = bool(payload.get("include_live_enrichment", False))
        external_inputs = payload.get("external_inputs")
        waivers = payload.get("waivers")
        
        # Normalize external_inputs: must be list of dicts or None
        if external_inputs is not None:
            if not isinstance(external_inputs, list):
                return 400, {
                    "status": "error",
                    "error_code": "INVALID_EXTERNAL_INPUTS",
                    "message": "external_inputs must be a list of objects or null",
                }
            # Validate each item is a dict
            for item in external_inputs:
                if not isinstance(item, dict):
                    return 400, {
                        "status": "error",
                        "error_code": "INVALID_EXTERNAL_INPUTS",
                        "message": "each item in external_inputs must be an object",
                    }

        if waivers is not None:
            if not isinstance(waivers, list):
                return 400, {
                    "status": "error",
                    "error_code": "INVALID_WAIVERS",
                    "message": "waivers must be a list of finding identifiers or objects",
                }
            for item in waivers:
                if not isinstance(item, (str, dict)):
                    return 400, {
                        "status": "error",
                        "error_code": "INVALID_WAIVERS",
                        "message": "each waiver must be a string or object",
                    }

        result = run_security_check(
            project_dir=self.project_dir,
            scope=scope,
            include_live_enrichment=include_live_enrichment,
            external_inputs=external_inputs,
            waivers=waivers,
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

    def claim_judge(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        claims = payload.get("claims")
        if not isinstance(claims, list):
            return 400, {
                "status": "error",
                "error_code": "INVALID_CLAIM_INPUT",
                "message": "claims must be a list",
            }
        result = judge_claims(self.project_dir, claims)
        return 200, result

    def test_intent_lock(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        action = str(payload.get("action", "")).strip()

        if action == "lock":
            intent = payload.get("intent")
            if not isinstance(intent, dict):
                return 400, {
                    "status": "error",
                    "error_code": "INVALID_INTENT_INPUT",
                    "message": "intent must be an object",
                }
            result = lock_intent(self.project_dir, intent)
            return 200, result

        if action == "verify":
            lock_id = payload.get("lock_id")
            results = payload.get("results")
            if not isinstance(lock_id, str) or not lock_id.strip():
                return 400, {
                    "status": "error",
                    "error_code": "INVALID_INTENT_INPUT",
                    "message": "lock_id is required for verify action",
                }
            if not isinstance(results, dict):
                return 400, {
                    "status": "error",
                    "error_code": "INVALID_INTENT_INPUT",
                    "message": "results must be an object for verify action",
                }
            result = verify_intent(self.project_dir, lock_id, results)
            return 200, result

        return 400, {
            "status": "error",
            "error_code": "INVALID_INTENT_ACTION",
            "message": f"Unknown action: {action!r}; expected 'lock' or 'verify'",
        }

    def mutation_gate_check(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")

        tool = payload.get("tool")
        file_path = payload.get("file_path")
        lock_id = payload.get("lock_id")
        exemption = payload.get("exemption")

        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("tool is required")
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("file_path is required")
        if lock_id is not None and not isinstance(lock_id, str):
            raise ValueError("lock_id must be a string when provided")
        if exemption is not None and not isinstance(exemption, str):
            raise ValueError("exemption must be a string when provided")

        result = check_mutation_allowed(
            tool=tool,
            file_path=file_path,
            project_dir=self.project_dir,
            lock_id=lock_id,
            exemption=exemption,
        )
        return 200, result

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
