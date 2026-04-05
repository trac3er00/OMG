export interface ToolCallRecord {
  readonly tool: string;
  readonly success: boolean;
  readonly latencyMs: number;
  readonly timestamp: string;
}

export interface ToolStats {
  readonly count: number;
  readonly successCount: number;
  readonly failCount: number;
  readonly totalLatencyMs: number;
  readonly avgLatencyMs: number;
  readonly successRate: number;
}

export interface AnalyticsSummary {
  readonly totalCalls: number;
  readonly overallSuccessRate: number;
  readonly avgLatencyMs: number;
  readonly byTool: Readonly<Record<string, ToolStats>>;
  readonly hotspots: readonly FileHotspot[];
  readonly errorTrend: ErrorTrend;
  readonly toolShifts: readonly ToolShift[];
}

export interface FileHotspot {
  readonly file: string;
  readonly editCount: number;
  readonly lastEdited: string;
}

export interface ErrorTrend {
  readonly trend: "stable" | "increasing" | "decreasing";
  readonly recentRate: number;
  readonly baselineRate: number;
}

export interface ToolShift {
  readonly tool: string;
  readonly changePct: number;
  readonly direction: "up" | "down";
}

export class AnalyticsHook {
  private readonly records: ToolCallRecord[] = [];
  private readonly fileEdits = new Map<string, { count: number; lastEdited: string }>();

  recordToolCall(tool: string, success: boolean, latencyMs: number): void {
    this.records.push({
      tool,
      success,
      latencyMs,
      timestamp: new Date().toISOString(),
    });
  }

  recordFileEdit(filePath: string): void {
    const existing = this.fileEdits.get(filePath);
    this.fileEdits.set(filePath, {
      count: (existing?.count ?? 0) + 1,
      lastEdited: new Date().toISOString(),
    });
  }

  getSummary(): AnalyticsSummary {
    const byTool: Record<string, { count: number; successCount: number; failCount: number; totalLatencyMs: number }> = {};

    for (const rec of this.records) {
      if (byTool[rec.tool] === undefined) {
        byTool[rec.tool] = { count: 0, successCount: 0, failCount: 0, totalLatencyMs: 0 };
      }
      byTool[rec.tool].count += 1;
      byTool[rec.tool].totalLatencyMs += rec.latencyMs;
      if (rec.success) {
        byTool[rec.tool].successCount += 1;
      } else {
        byTool[rec.tool].failCount += 1;
      }
    }

    const toolStats: Record<string, ToolStats> = {};
    for (const [tool, raw] of Object.entries(byTool)) {
      toolStats[tool] = {
        count: raw.count,
        successCount: raw.successCount,
        failCount: raw.failCount,
        totalLatencyMs: raw.totalLatencyMs,
        avgLatencyMs: raw.count > 0 ? Math.round(raw.totalLatencyMs / raw.count) : 0,
        successRate: raw.count > 0 ? raw.successCount / raw.count : 0,
      };
    }

    const totalCalls = this.records.length;
    const totalSuccess = this.records.filter((r) => r.success).length;
    const totalLatency = this.records.reduce((sum, r) => sum + r.latencyMs, 0);

    return {
      totalCalls,
      overallSuccessRate: totalCalls > 0 ? totalSuccess / totalCalls : 0,
      avgLatencyMs: totalCalls > 0 ? Math.round(totalLatency / totalCalls) : 0,
      byTool: toolStats,
      hotspots: this.computeHotspots(),
      errorTrend: this.computeErrorTrend(),
      toolShifts: this.computeToolShifts(byTool),
    };
  }

  private computeHotspots(): FileHotspot[] {
    const hotspots: FileHotspot[] = [];
    for (const [file, data] of this.fileEdits) {
      if (data.count > 5) {
        hotspots.push({
          file,
          editCount: data.count,
          lastEdited: data.lastEdited,
        });
      }
    }
    hotspots.sort((a, b) => b.editCount - a.editCount);
    return hotspots;
  }

  private computeErrorTrend(): ErrorTrend {
    if (this.records.length === 0) {
      return { trend: "stable", recentRate: 0, baselineRate: 0 };
    }
    const midpoint = Math.floor(this.records.length / 2);
    const older = this.records.slice(0, midpoint);
    const recent = this.records.slice(midpoint);

    const olderFailRate = older.length > 0
      ? older.filter((r) => !r.success).length / older.length
      : 0;
    const recentFailRate = recent.length > 0
      ? recent.filter((r) => !r.success).length / recent.length
      : 0;

    let trend: "stable" | "increasing" | "decreasing" = "stable";
    if (olderFailRate === 0 && recentFailRate > 0) {
      trend = "increasing";
    } else if (olderFailRate > 0) {
      const delta = (recentFailRate - olderFailRate) / olderFailRate;
      if (delta > 0.1) trend = "increasing";
      else if (delta < -0.1) trend = "decreasing";
    }

    return {
      trend,
      recentRate: Math.round(recentFailRate * 1000) / 1000,
      baselineRate: Math.round(olderFailRate * 1000) / 1000,
    };
  }

  private computeToolShifts(
    byTool: Record<string, { count: number }>,
  ): ToolShift[] {
    const counts = Object.values(byTool).map((s) => s.count);
    if (counts.length === 0) return [];

    const baseline = counts.reduce((a, b) => a + b, 0) / counts.length;
    if (baseline <= 0) return [];

    const shifts: ToolShift[] = [];
    for (const [tool, stats] of Object.entries(byTool)) {
      const changePct = ((stats.count - baseline) / baseline) * 100;
      if (Math.abs(changePct) > 20) {
        shifts.push({
          tool,
          changePct: Math.round(changePct * 100) / 100,
          direction: changePct > 0 ? "up" : "down",
        });
      }
    }
    shifts.sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct));
    return shifts;
  }
}
