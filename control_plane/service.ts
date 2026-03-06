import { createEvidencePack } from "../hooks/shadow_manager.ts";
import { evaluateBashCommand, evaluateFileAccess } from "../hooks/policy_engine.ts";
import { reviewConfigChange } from "../hooks/trust_review.ts";
import { runPipeline } from "../lab/pipeline.ts";
import { verifyArtifact } from "../registry/verify_artifact.ts";
import { dispatchRuntime } from "../runtime/dispatcher.ts";

type JsonMap = Record<string, unknown>;

function isRecord(value: unknown): value is JsonMap {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function invalid(error_code: string, message: string) {
  return [400, { status: "error", error_code, message }] as const;
}

export class ControlPlaneService {
  project_dir: string;

  constructor(projectDir?: string) {
    this.project_dir = projectDir || process.env.CLAUDE_PROJECT_DIR || process.cwd();
  }

  policyEvaluate(payload: JsonMap) {
    const tool = String(payload.tool || "");
    const input = isRecord(payload.input) ? payload.input : {};

    if (tool === "Bash") {
      return [200, evaluateBashCommand(String(input.command || ""))] as const;
    }

    if (["Read", "Write", "Edit", "MultiEdit"].includes(tool)) {
      return [200, evaluateFileAccess(tool, String(input.file_path || input.filePath || ""))] as const;
    }

    if (tool === "SupplyArtifact") {
      return [200, verifyArtifact(isRecord(payload.artifact) ? payload.artifact : {}, String(payload.mode || "warn_and_run"))] as const;
    }

    return invalid("INVALID_POLICY_INPUT", "Unsupported tool for policy evaluation");
  }

  trustReview(payload: JsonMap) {
    const file_path = String(payload.file_path || "settings.json");
    const old_config = isRecord(payload.old_config) ? payload.old_config : null;
    const new_config = isRecord(payload.new_config) ? payload.new_config : null;

    if (!old_config || !new_config) {
      return invalid("INVALID_TRUST_INPUT", "old_config and new_config must be objects");
    }

    return [200, reviewConfigChange(file_path, old_config, new_config)] as const;
  }

  evidenceIngest(payload: JsonMap) {
    const run_id = String(payload.run_id || "").trim();
    if (!run_id) {
      return invalid("INVALID_EVIDENCE_INPUT", "run_id is required");
    }

    const required = ["tests", "security_scans", "diff_summary", "reproducibility", "unresolved_risks"];
    const missing = required.filter((key) => !(key in payload));
    if (missing.length > 0) {
      return invalid("INVALID_EVIDENCE_INPUT", `Missing required fields: ${missing.join(", ")}`);
    }

    const path = createEvidencePack(this.project_dir, run_id, {
      tests: Array.isArray(payload.tests) ? payload.tests : [],
      security_scans: Array.isArray(payload.security_scans) ? payload.security_scans : [],
      diff_summary: isRecord(payload.diff_summary) ? payload.diff_summary : {},
      reproducibility: isRecord(payload.reproducibility) ? payload.reproducibility : {},
      unresolved_risks: Array.isArray(payload.unresolved_risks) ? payload.unresolved_risks.map(String) : []
    });

    return [
      202,
      {
        status: "accepted",
        run_id,
        evidence_path: path.replace(`${this.project_dir}/`, "")
      }
    ] as const;
  }

  runtimeDispatch(payload: JsonMap) {
    const runtime = String(payload.runtime || "").trim();
    const idea = isRecord(payload.idea) ? payload.idea : null;

    if (!runtime) {
      return invalid("INVALID_RUNTIME_INPUT", "runtime is required");
    }
    if (!idea) {
      return invalid("INVALID_RUNTIME_INPUT", "idea must be an object");
    }

    const result = dispatchRuntime(runtime, idea);
    return [result.status === "error" ? 400 : 200, result] as const;
  }

  registryVerify(payload: JsonMap) {
    const artifact = isRecord(payload.artifact) ? payload.artifact : null;
    if (!artifact) {
      return invalid("INVALID_REGISTRY_INPUT", "artifact must be an object");
    }
    return [200, verifyArtifact(artifact, String(payload.mode || "warn_and_run"))] as const;
  }

  labJobs(payload: JsonMap) {
    const result = runPipeline(payload);
    return [result.status === "ready" || result.status === "failed_evaluation" ? 201 : 400, result] as const;
  }

  scoreboardBaseline() {
    return [
      200,
      {
        generated_at: new Date().toISOString(),
        baseline: {
          safe_autonomy_rate: 0,
          pr_throughput: 0,
          adoption_velocity: 0
        },
        target_policy: "non-regression-or-better"
      }
    ] as const;
  }
}
