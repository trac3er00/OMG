export interface ReadCompletenessResult {
  detected: boolean;
  coveragePercent: number;
  totalLines: number;
  linesRead: number;
  warningMessage?: string;
}

export function checkReadCompleteness(
  totalLines: number,
  linesRead: number,
): ReadCompletenessResult {
  const coveragePercent =
    totalLines === 0 ? 100 : (linesRead / totalLines) * 100;
  const detected = coveragePercent < 80;
  const warningMessage = detected
    ? `Only ${coveragePercent.toFixed(1)}% of file read (${linesRead}/${totalLines} lines). Read the complete file before making changes.`
    : undefined;
  return {
    detected,
    coveragePercent,
    totalLines,
    linesRead,
    ...(warningMessage ? { warningMessage } : {}),
  };
}

export interface TruncationResult {
  detected: boolean;
  truncationPatterns: string[];
  warningMessage?: string;
}

const TRUNCATION_PATTERNS = [
  /showing (?:first|only) \d+/i,
  /truncated for brevity/i,
  /\.\.\. and \d+ more/i,
  /for conciseness/i,
  /omitting remaining/i,
  /see full output/i,
];

export function detectCourtesyCut(output: string): TruncationResult {
  const matched = TRUNCATION_PATTERNS.filter((p) => p.test(output)).map((p) =>
    p.toString(),
  );
  const detected = matched.length > 0;
  const warningMessage = detected
    ? `Output truncation detected (${matched.length} pattern(s)). Provide complete output or get explicit user consent for truncation.`
    : undefined;
  return {
    detected,
    truncationPatterns: matched,
    ...(warningMessage ? { warningMessage } : {}),
  };
}

export interface ChecklistResult {
  detected: boolean;
  totalItems: number;
  checkedItems: number;
  coveragePercent: number;
  warningMessage?: string;
}

export function checkChecklistCompleteness(
  totalItems: number,
  checkedItems: number,
): ChecklistResult {
  const coveragePercent =
    totalItems === 0 ? 100 : (checkedItems / totalItems) * 100;
  const detected = coveragePercent < 100;
  const warningMessage = detected
    ? `Only ${checkedItems}/${totalItems} checklist items verified (${coveragePercent.toFixed(1)}%). All items must be verified.`
    : undefined;
  return {
    detected,
    totalItems,
    checkedItems,
    coveragePercent,
    ...(warningMessage ? { warningMessage } : {}),
  };
}
