export interface AgentOutput {
  agentId: string;
  claim: string;
  confidence: number;
  evidence?: string[];
}

export interface ContradictionPair {
  outputA: AgentOutput;
  outputB: AgentOutput;
  reason: string;
}

export interface MergeValidationResult {
  hasContradiction: boolean;
  contradictions: ContradictionPair[];
  validatedOutputs: AgentOutput[];
  warningMessage?: string;
}

const OPPOSING_PAIRS: [string, string][] = [
  ["jwt", "session"],
  ["enable", "disable"],
  ["add", "remove"],
  ["increase", "decrease"],
  ["sync", "async"],
  ["use", "avoid"],
  ["postgresql", "mysql"],
];

export function validateMerge(outputs: AgentOutput[]): MergeValidationResult {
  const contradictions: ContradictionPair[] = [];

  for (let i = 0; i < outputs.length; i++) {
    for (let j = i + 1; j < outputs.length; j++) {
      const a = outputs[i].claim.toLowerCase();
      const b = outputs[j].claim.toLowerCase();

      for (const [termA, termB] of OPPOSING_PAIRS) {
        if (
          (a.includes(termA) && b.includes(termB)) ||
          (a.includes(termB) && b.includes(termA))
        ) {
          contradictions.push({
            outputA: outputs[i],
            outputB: outputs[j],
            reason: `Opposing: "${termA}" vs "${termB}"`,
          });
          break;
        }
      }
    }
  }

  const warningMessage =
    contradictions.length > 0
      ? `${contradictions.length} contradictions detected.`
      : undefined;

  return {
    hasContradiction: contradictions.length > 0,
    contradictions,
    validatedOutputs: outputs,
    ...(warningMessage ? { warningMessage } : {}),
  };
}
