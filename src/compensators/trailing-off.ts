export interface TaskItem {
  id: string;
  content: string;
  lineCount: number;
  wordCount?: number;
}

export interface TrailingOffResult {
  detected: boolean;
  qualityRatio: number;
  firstGroupAvg: number;
  lastGroupAvg: number;
  correctionMessage?: string;
}

function average(nums: number[]): number {
  return nums.length === 0 ? 0 : nums.reduce((a, b) => a + b, 0) / nums.length;
}

export function detectTrailingOff(items: TaskItem[]): TrailingOffResult {
  if (items.length < 5) {
    return { detected: false, qualityRatio: 1.0, firstGroupAvg: 0, lastGroupAvg: 0 };
  }

  const firstThirdCount = Math.ceil(items.length * 0.3);
  const lastThirdCount = Math.ceil(items.length * 0.3);

  const firstGroup = items.slice(0, firstThirdCount);
  const lastGroup = items.slice(items.length - lastThirdCount);

  const firstGroupAvg = average(firstGroup.map((i) => i.lineCount));
  const lastGroupAvg = average(lastGroup.map((i) => i.lineCount));

  const qualityRatio = firstGroupAvg === 0 ? 1 : lastGroupAvg / firstGroupAvg;
  const detected = qualityRatio < 0.7;

  if (!detected) {
    return {
      detected,
      qualityRatio,
      firstGroupAvg,
      lastGroupAvg,
    };
  }

  return {
    detected,
    qualityRatio,
    firstGroupAvg,
    lastGroupAvg,
    correctionMessage: `Quality degradation detected: last items average ${lastGroupAvg.toFixed(1)} lines vs first items ${firstGroupAvg.toFixed(1)} lines. Ensure remaining items receive equal attention.`,
  };
}
