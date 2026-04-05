export interface SessionObservation {
  timestamp: number;
  goal: string;
  output: string;
  consensusScore?: number;
  toolsUsed?: string[];
}

export interface DriftScores {
  semanticDrift: number;
  coordinationDrift: number;
  behavioralDrift: number;
  asi: number; // Agent Stability Index = 1 - max(drifts)
}

export interface DriftReport {
  sessionId?: string;
  scores: DriftScores;
  detected: boolean;
  dominantDriftType?: "semantic" | "coordination" | "behavioral";
  message?: string;
  timestamp: number;
}

function average(nums: number[]): number {
  return nums.length === 0 ? 0 : nums.reduce((a, b) => a + b, 0) / nums.length;
}

function semanticSimilarity(a: string, b: string): number {
  const wordsA = new Set(a.toLowerCase().split(/\W+/).filter((w) => w.length > 3));
  const wordsB = new Set(b.toLowerCase().split(/\W+/).filter((w) => w.length > 3));
  if (wordsA.size === 0 || wordsB.size === 0) return 0;
  const intersection = [...wordsA].filter((w) => wordsB.has(w)).length;
  return intersection / Math.max(wordsA.size, wordsB.size);
}

export function computeASI(observations: SessionObservation[]): DriftReport {
  if (observations.length < 2) {
    return {
      scores: { semanticDrift: 0, coordinationDrift: 0, behavioralDrift: 0, asi: 1.0 },
      detected: false,
      timestamp: Date.now(),
    };
  }

  const half = Math.floor(observations.length / 2);
  const firstHalf = observations.slice(0, half);
  const secondHalf = observations.slice(half);

  const earlyAlignment = average(firstHalf.map((o) => semanticSimilarity(o.goal, o.output)));
  const lateAlignment = average(secondHalf.map((o) => semanticSimilarity(o.goal, o.output)));
  const semanticDrift = earlyAlignment === 0 ? 0 : Math.max(0, 1 - lateAlignment / earlyAlignment);

  const withConsensus = observations.filter((o) => o.consensusScore !== undefined);
  const coordinationDrift =
    withConsensus.length === 0 ? 0 : Math.max(0, 1 - average(withConsensus.map((o) => o.consensusScore!)));

  const earlyTools = new Set(firstHalf.flatMap((o) => o.toolsUsed ?? []));
  const lateNewTools = secondHalf.flatMap((o) => o.toolsUsed ?? []).filter((t) => !earlyTools.has(t));
  const allTools = new Set([...earlyTools, ...lateNewTools]);
  const behavioralDrift = allTools.size === 0 ? 0 : lateNewTools.length / allTools.size;

  const maxDrift = Math.max(semanticDrift, coordinationDrift, behavioralDrift);
  const asi = 1 - maxDrift;
  const detected = maxDrift > 0.5;

  const driftTypes = [
    { type: "semantic" as const, value: semanticDrift },
    { type: "coordination" as const, value: coordinationDrift },
    { type: "behavioral" as const, value: behavioralDrift },
  ].sort((a, b) => b.value - a.value);

  const report: DriftReport = {
    scores: { semanticDrift, coordinationDrift, behavioralDrift, asi },
    detected,
    timestamp: Date.now(),
  };

  if (detected) {
    report.dominantDriftType = driftTypes[0].type;
    report.message = `Agent drift detected (ASI: ${asi.toFixed(2)}). Dominant: ${driftTypes[0].type}`;
  }

  return report;
}
