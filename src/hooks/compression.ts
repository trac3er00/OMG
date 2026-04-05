export interface CompressionGuidelines {
  readonly generatedAt: string;
  readonly alwaysKeep: readonly string[];
  readonly preferKeep: readonly string[];
  readonly compressOk: readonly string[];
  readonly dropOk: readonly string[];
}

export interface FeedbackEntry {
  readonly ts: string;
  readonly sessionId: string;
  readonly toolName: string;
  readonly failureReason: string;
  readonly postCompaction: boolean;
  readonly matchedItems: readonly string[];
  readonly promotedItems: readonly string[];
}

export interface CompressionDeps {
  readonly readLines: (path: string) => Promise<readonly string[]>;
  readonly exists: (path: string) => Promise<boolean>;
  readonly writeJson: (path: string, data: unknown) => Promise<void>;
}

const PROMOTION_THRESHOLD = 3;

export class CompressionHook {
  private readonly deps: CompressionDeps | undefined;

  constructor(deps?: CompressionDeps) {
    this.deps = deps;
  }

  shouldCompress(contextSize: number, limit: number): boolean {
    return contextSize > limit;
  }

  compress(content: string, maxLength?: number): string {
    const limit = maxLength ?? Math.floor(content.length * 0.7);
    if (content.length <= limit) return content;

    const lines = content.split("\n");
    const scored = lines.map((line) => ({
      line,
      priority: scoreLine(line),
    }));
    scored.sort((a, b) => b.priority - a.priority);

    const kept: string[] = [];
    let total = 0;
    for (const entry of scored) {
      if (total + entry.line.length + 1 > limit) break;
      kept.push(entry.line);
      total += entry.line.length + 1;
    }

    return kept.join("\n");
  }

  async optimizeGuidelines(
    feedbackPath: string,
    outputPath: string,
  ): Promise<CompressionGuidelines> {
    const empty = newGuidelines();
    if (this.deps === undefined) return empty;

    const feedbackExists = await this.deps.exists(feedbackPath);
    if (!feedbackExists) return empty;

    const { failureCounts, allItems } = await readFeedback(
      this.deps,
      feedbackPath,
    );

    const alwaysKeep = Array.from(failureCounts.entries())
      .filter(([_, count]) => count >= 3)
      .map(([item]) => item)
      .sort();

    const preferKeep = Array.from(failureCounts.entries())
      .filter(([_, count]) => count >= 1 && count <= 2)
      .map(([item]) => item)
      .sort();

    const compressOk = Array.from(allItems)
      .filter((item) => (failureCounts.get(item) ?? 0) === 0)
      .sort();

    const guidelines: CompressionGuidelines = {
      ...empty,
      alwaysKeep,
      preferKeep,
      compressOk,
    };

    if (outputPath) {
      await this.deps.writeJson(outputPath, guidelines);
    }

    return guidelines;
  }

  computePromotions(
    entries: readonly FeedbackEntry[],
    matchedItems: readonly string[],
  ): string[] {
    const promoted: string[] = [];
    for (const item of matchedItems) {
      let count = 0;
      for (const row of entries) {
        if (row.matchedItems.includes(item)) {
          count += 1;
        }
      }
      if (count >= PROMOTION_THRESHOLD) {
        promoted.push(item);
      }
    }
    return [...new Set(promoted)].sort();
  }
}

function newGuidelines(): CompressionGuidelines {
  return {
    generatedAt: new Date().toISOString(),
    alwaysKeep: [],
    preferKeep: [],
    compressOk: [],
    dropOk: [],
  };
}

function scoreLine(line: string): number {
  const trimmed = line.trim();
  if (!trimmed) return 0;
  if (trimmed.startsWith("#")) return 10;
  if (trimmed.startsWith("-") || trimmed.startsWith("*")) return 7;
  if (trimmed.match(/^(export|import|function|class|const|let|def )/)) return 8;
  if (trimmed.startsWith("//") || trimmed.startsWith("/*")) return 1;
  return 5;
}

interface FeedbackReadResult {
  readonly failureCounts: Map<string, number>;
  readonly allItems: Set<string>;
}

function isFailureEntry(entry: Record<string, unknown>): boolean {
  if (entry["failed"] === true) return true;
  if (entry["success"] === false) return true;
  const status = String(entry["status"] ?? "").trim().toLowerCase();
  if (status === "failed" || status === "failure" || status === "error") return true;
  const outcome = String(entry["outcome"] ?? "").trim().toLowerCase();
  return outcome === "failed" || outcome === "failure" || outcome === "error";
}

function extractDroppedItems(entry: Record<string, unknown>): string[] {
  for (const key of ["dropped_items", "dropped", "items_dropped", "dropped_context"]) {
    const raw = entry[key];
    if (Array.isArray(raw)) {
      return raw
        .filter((v): v is string => typeof v === "string")
        .map((s) => s.trim())
        .filter(Boolean);
    }
  }
  return [];
}

async function readFeedback(
  deps: CompressionDeps,
  path: string,
): Promise<FeedbackReadResult> {
  const failureCounts = new Map<string, number>();
  const allItems = new Set<string>();

  const lines = await deps.readLines(path);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    let entry: Record<string, unknown>;
    try {
      entry = JSON.parse(line) as Record<string, unknown>;
    } catch {
      continue;
    }

    const droppedItems = extractDroppedItems(entry);
    if (droppedItems.length === 0) continue;

    for (const item of droppedItems) {
      allItems.add(item);
    }

    if (isFailureEntry(entry)) {
      for (const item of new Set(droppedItems)) {
        failureCounts.set(item, (failureCounts.get(item) ?? 0) + 1);
      }
    }
  }

  return { failureCounts, allItems };
}
