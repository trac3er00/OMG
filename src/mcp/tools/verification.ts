import type { ToolRegistration } from "../../interfaces/mcp.js";
import {
  judgeClaimBatch,
  type Claim,
  type EvidenceRef,
} from "../../verification/claim-judge.js";
import { TestIntentLock } from "../../verification/test-intent-lock.js";
import { EvidenceRegistry } from "../../evidence/registry.js";
import { detectInjection } from "../../security/injection-defense.js";

function resolveProjectDir(args: Readonly<Record<string, unknown>>): string {
  if (typeof args.project_dir === "string" && args.project_dir.length > 0) {
    return args.project_dir;
  }
  return process.env.CLAUDE_PROJECT_DIR ?? process.cwd();
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

/**
 * MCP tool: omg_claim_judge
 *
 * Accepts claims with evidence and returns a batch verdict.
 * Input: { claims: string[], evidence: object[] }
 * Output: { verdict, results }
 */
export function createClaimJudgeTool(): ToolRegistration {
  return {
    name: "omg_claim_judge",
    description:
      "Judge claims against evidence. Accepts an array of claim strings and evidence objects, returns a batch verdict.",
    inputSchema: {
      type: "object",
      properties: {
        claims: {
          type: "array",
          items: { type: "string" },
          description: "Array of claim text strings to evaluate",
        },
        evidence: {
          type: "array",
          items: {
            type: "object",
            properties: {
              type: { type: "string" },
              path: { type: "string" },
              valid: { type: "boolean" },
            },
          },
          description: "Array of evidence references to support claims",
        },
      },
      required: ["claims", "evidence"],
    },
    handler: async (
      args: Readonly<Record<string, unknown>>,
    ): Promise<unknown> => {
      const rawClaims = args.claims;
      const rawEvidence = args.evidence;

      if (!Array.isArray(rawClaims)) {
        throw new Error("claims must be an array of strings");
      }
      if (!Array.isArray(rawEvidence)) {
        throw new Error("evidence must be an array of objects");
      }

      const evidenceRefs: EvidenceRef[] = rawEvidence.map(
        (e: Record<string, unknown>): EvidenceRef => ({
          type: typeof e.type === "string" ? e.type : "unknown",
          ...(typeof e.path === "string" ? { path: e.path } : {}),
          ...(typeof e.valid === "boolean" ? { valid: e.valid } : {}),
        }),
      );

      const claims: Claim[] = rawClaims.map((text: unknown) => ({
        text: String(text),
        evidence: evidenceRefs,
      }));

      const batch = judgeClaimBatch(claims);

      return {
        verdict: batch.aggregateVerdict,
        results: batch.results,
        totalClaims: batch.totalClaims,
        acceptedCount: batch.acceptedCount,
        rejectedCount: batch.rejectedCount,
      };
    },
  };
}

/**
 * MCP tool: omg_test_intent_lock
 *
 * Manages the TDD intent lock state.
 * Input: { action: "lock" | "unlock" | "check", test_file?: string }
 * Output: { locked, status }
 */
export function createTestIntentLockTool(): ToolRegistration {
  return {
    name: "omg_test_intent_lock",
    description:
      "Manage TDD intent lock. Lock, unlock, or check current lock state for test-driven development enforcement.",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["lock", "unlock", "check"],
          description: "The action to perform on the lock",
        },
        test_file: {
          type: "string",
          description: "Optional test file path for context",
        },
      },
      required: ["action"],
    },
    handler: async (
      args: Readonly<Record<string, unknown>>,
    ): Promise<unknown> => {
      const action = requireString(args.action, "action");
      const projectDir = resolveProjectDir(args);
      const lock = new TestIntentLock(projectDir);

      if (action === "lock") {
        const runId =
          typeof args.test_file === "string"
            ? args.test_file
            : `run-${Date.now()}`;
        lock.acquire(runId);
        return {
          locked: true,
          status: "locked",
          runId,
        };
      }

      if (action === "unlock") {
        const state = lock.lockState();
        if (state.locked && state.runId) {
          lock.release(state.runId);
        }
        return {
          locked: false,
          status: "unlocked",
        };
      }

      if (action === "check") {
        const state = lock.lockState();
        return {
          locked: state.locked,
          status: state.locked ? "locked" : "unlocked",
          runId: state.runId,
          lockedAt: state.lockedAt,
        };
      }

      throw new Error(`Invalid action: ${action}. Must be lock, unlock, or check.`);
    },
  };
}

/**
 * MCP tool: omg_evidence_ingest
 *
 * Registers evidence artifacts into the evidence registry.
 * Input: { type: string, path: string, content?: string }
 * Output: { id, registered }
 */
export function createEvidenceIngestTool(): ToolRegistration {
  return {
    name: "omg_evidence_ingest",
    description:
      "Ingest evidence into the registry. Registers an evidence artifact with type, path, and optional content.",
    inputSchema: {
      type: "object",
      properties: {
        type: {
          type: "string",
          description: "Evidence type (e.g. junit, coverage, sarif, browser_trace)",
        },
        path: {
          type: "string",
          description: "Path to the evidence artifact",
        },
        content: {
          type: "string",
          description: "Optional inline content for the evidence",
        },
      },
      required: ["type", "path"],
    },
    handler: async (
      args: Readonly<Record<string, unknown>>,
    ): Promise<unknown> => {
      const type = requireString(args.type, "type");
      const path = requireString(args.path, "path");
      const projectDir = resolveProjectDir(args);
      const runId = `ingest-${Date.now()}`;

      const registry = new EvidenceRegistry(projectDir);
      registry.register({
        type,
        runId,
        path,
        valid: true,
        ...(typeof args.content === "string"
          ? { metadata: { content: args.content } }
          : {}),
      });

      return {
        id: runId,
        registered: true,
        type,
        path,
      };
    },
  };
}

/**
 * MCP tool: omg_security_check
 *
 * Runs injection detection / security analysis on content.
 * Input: { target: string, check_type: string }
 * Output: { passed, findings }
 */
export function createSecurityCheckTool(): ToolRegistration {
  return {
    name: "omg_security_check",
    description:
      "Run security checks on content. Detects prompt injection, role manipulation, and other security threats.",
    inputSchema: {
      type: "object",
      properties: {
        target: {
          type: "string",
          description: "The content to analyze for security threats",
        },
        check_type: {
          type: "string",
          description: "Type of security check to perform (e.g. injection, boundary, structural)",
        },
      },
      required: ["target", "check_type"],
    },
    handler: async (
      args: Readonly<Record<string, unknown>>,
    ): Promise<unknown> => {
      const target = requireString(args.target, "target");
      requireString(args.check_type, "check_type");

      const result = detectInjection(target);

      return {
        passed: !result.detected,
        findings: {
          detected: result.detected,
          confidence: result.confidence,
          layers: result.layers,
          patterns: result.patterns,
          explanation: result.explanation,
        },
      };
    },
  };
}

export function createVerificationTools(): readonly ToolRegistration[] {
  return [
    createClaimJudgeTool(),
    createTestIntentLockTool(),
    createEvidenceIngestTool(),
    createSecurityCheckTool(),
  ];
}
