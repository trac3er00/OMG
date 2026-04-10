// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LogEntry {
  readonly timestamp: string;
  readonly level: "error" | "warn" | "info" | "debug";
  readonly message: string;
  readonly source?: string;
}

export interface ErrorPattern {
  readonly message: string;
  readonly count: number;
  readonly firstSeen: string;
  readonly lastSeen: string;
}

export interface MonitorReport {
  readonly totalLines: number;
  readonly errorCount: number;
  readonly warnCount: number;
  readonly errorPatterns: readonly ErrorPattern[];
  readonly wasteIndicators: readonly WasteIndicator[];
}

export interface WasteIndicator {
  readonly type: "repeated_error" | "duplicate_action" | "context_rebuild";
  readonly description: string;
  readonly severity: "low" | "medium" | "high";
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Matches: [2024-01-01T12:00:00Z] ERROR msg  or  2024-01-01 12:00:00 WARN msg
const LOG_LINE_REGEX =
  /^\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\]]*)\]?\s*(ERROR|WARN|INFO|DEBUG)\s+(.+)$/i;

const REPEATED_ERROR_MIN = 3;
const DUPLICATE_ACTION_MIN = 2;
const CONTEXT_REBUILD_KEYWORDS = [
  "rebuilding context",
  "context expired",
  "cache miss",
  "full reload",
  "session restart",
];

// ---------------------------------------------------------------------------
// LogMonitor
// ---------------------------------------------------------------------------

export class LogMonitor {
  parseLogContent(content: string): LogEntry[] {
    const lines = content.split("\n").filter((line) => line.trim().length > 0);
    const entries: LogEntry[] = [];

    for (const line of lines) {
      const match = LOG_LINE_REGEX.exec(line);
      if (match) {
        const [, timestamp, levelStr, message] = match;
        entries.push({
          timestamp: timestamp!,
          level: levelStr!.toLowerCase() as LogEntry["level"],
          message: message!.trim(),
        });
      }
    }

    return entries;
  }

  analyze(entries: readonly LogEntry[]): MonitorReport {
    const errorEntries = entries.filter((e) => e.level === "error");
    const warnEntries = entries.filter((e) => e.level === "warn");

    const errorPatterns = this.findErrorPatterns(errorEntries);
    const wasteIndicators = this.detectWasteIndicators(entries, errorPatterns);

    return {
      totalLines: entries.length,
      errorCount: errorEntries.length,
      warnCount: warnEntries.length,
      errorPatterns,
      wasteIndicators,
    };
  }

  analyzeContent(content: string): MonitorReport {
    const entries = this.parseLogContent(content);
    return this.analyze(entries);
  }

  // -------------------------------------------------------------------------
  // Pattern detection (pure string matching, no LLM)
  // -------------------------------------------------------------------------

  private findErrorPatterns(errors: readonly LogEntry[]): ErrorPattern[] {
    const buckets = new Map<
      string,
      { count: number; firstSeen: string; lastSeen: string }
    >();

    for (const entry of errors) {
      // Strip UUIDs, large numbers, and paths to group similar error messages
      const key = this.normalizeMessage(entry.message);
      const existing = buckets.get(key);
      if (existing) {
        existing.count++;
        existing.lastSeen = entry.timestamp;
      } else {
        buckets.set(key, {
          count: 1,
          firstSeen: entry.timestamp,
          lastSeen: entry.timestamp,
        });
      }
    }

    return [...buckets.entries()]
      .filter(([, v]) => v.count >= 1)
      .map(([message, v]) => ({
        message,
        count: v.count,
        firstSeen: v.firstSeen,
        lastSeen: v.lastSeen,
      }))
      .sort((a, b) => b.count - a.count);
  }

  private normalizeMessage(message: string): string {
    return message
      .replace(
        /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi,
        "<UUID>",
      )
      .replace(/\b\d{4,}\b/g, "<NUM>")
      .replace(/\/[^\s]+/g, "<PATH>")
      .trim();
  }

  private detectWasteIndicators(
    entries: readonly LogEntry[],
    errorPatterns: readonly ErrorPattern[],
  ): WasteIndicator[] {
    const indicators: WasteIndicator[] = [];

    for (const pattern of errorPatterns) {
      if (pattern.count >= REPEATED_ERROR_MIN) {
        indicators.push({
          type: "repeated_error",
          description: `"${pattern.message}" occurred ${pattern.count} times`,
          severity: pattern.count >= 10 ? "high" : "medium",
        });
      }
    }

    const infoBuckets = new Map<string, number>();
    for (const entry of entries) {
      if (entry.level === "info") {
        const key = this.normalizeMessage(entry.message);
        infoBuckets.set(key, (infoBuckets.get(key) ?? 0) + 1);
      }
    }
    for (const [message, count] of infoBuckets) {
      if (count >= DUPLICATE_ACTION_MIN) {
        indicators.push({
          type: "duplicate_action",
          description: `Action "${message}" repeated ${count} times`,
          severity: count >= 5 ? "medium" : "low",
        });
      }
    }

    let rebuildCount = 0;
    for (const entry of entries) {
      const lower = entry.message.toLowerCase();
      if (CONTEXT_REBUILD_KEYWORDS.some((kw) => lower.includes(kw))) {
        rebuildCount++;
      }
    }
    if (rebuildCount > 0) {
      indicators.push({
        type: "context_rebuild",
        description: `Detected ${rebuildCount} context rebuild event(s)`,
        severity: rebuildCount >= 3 ? "high" : "low",
      });
    }

    return indicators;
  }
}
