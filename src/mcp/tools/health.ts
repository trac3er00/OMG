import type { ToolRegistration } from "../../interfaces/mcp.js";
import { SessionHealthProvider } from "../../runtime/session-health.js";

export interface GuideAssertInput {
  readonly assertion: string;
  readonly evidence?: Readonly<Record<string, unknown>>;
}

export interface GuideAssertResult {
  readonly passed: boolean;
  readonly message: string;
}

function validateGuideAssert(args: Readonly<Record<string, unknown>>): GuideAssertInput {
  const assertion = args.assertion;
  if (typeof assertion !== "string" || assertion.trim().length === 0) {
    throw new Error("assertion must be a non-empty string");
  }

  const evidence = args.evidence;
  if (evidence !== undefined && (typeof evidence !== "object" || evidence === null || Array.isArray(evidence))) {
    throw new Error("evidence must be an object when provided");
  }

  if (evidence === undefined) {
    return { assertion: assertion.trim() };
  }

  const typedEvidence = evidence as Readonly<Record<string, unknown>>;

  return {
    assertion: assertion.trim(),
    evidence: typedEvidence,
  };
}

function evaluateAssertion(input: GuideAssertInput): GuideAssertResult {
  const text = input.assertion.toLowerCase();

  const negativeMarkers = ["todo", "fixme", "hack", "placeholder", "insecure", "broken"];
  for (const marker of negativeMarkers) {
    if (text.includes(marker)) {
      return {
        passed: false,
        message: `Assertion contains non-production marker: "${marker}"`,
      };
    }
  }

  if (input.evidence !== undefined) {
    const evidenceKeys = Object.keys(input.evidence);
    if (evidenceKeys.length === 0) {
      return {
        passed: false,
        message: "Evidence object is empty — no supporting data provided",
      };
    }
  }

  return {
    passed: true,
    message: "Assertion accepted",
  };
}

export function createSessionHealthTool(provider: SessionHealthProvider): ToolRegistration {
  return {
    name: "omg_get_session_health",
    description: "Returns current session health status including defense risk level and tool count",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string", description: "Optional session identifier" },
      },
    },
    handler: async (args: Readonly<Record<string, unknown>>) => {
      const sessionId = typeof args.session_id === "string" ? args.session_id : undefined;
      return provider.getHealth(sessionId);
    },
  };
}

export function createGuideAssertTool(): ToolRegistration {
  return {
    name: "omg_guide_assert",
    description: "Validates an assertion string against evidence, returns pass/fail verdict",
    inputSchema: {
      type: "object",
      properties: {
        assertion: { type: "string", description: "The assertion to validate" },
        evidence: { type: "object", description: "Optional supporting evidence" },
      },
      required: ["assertion"],
    },
    handler: async (args: Readonly<Record<string, unknown>>) => {
      const input = validateGuideAssert(args);
      return evaluateAssertion(input);
    },
  };
}
