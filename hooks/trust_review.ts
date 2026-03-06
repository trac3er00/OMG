import { createHash } from "node:crypto";
import { join } from "node:path";
import { ensureDir, writeJsonFile } from "./_common.ts";

type RecordShape = Record<string, unknown>;

function safeRecord(value: unknown): RecordShape {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as RecordShape) : {};
}

function safeList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function collectMcpChanges(oldCfg: RecordShape, newCfg: RecordShape) {
  const oldServers = safeRecord(oldCfg.mcpServers);
  const newServers = safeRecord(newCfg.mcpServers);
  const names = new Set([...Object.keys(oldServers), ...Object.keys(newServers)]);
  const changes: RecordShape[] = [];
  for (const name of [...names].sort()) {
    const before = oldServers[name];
    const after = newServers[name];
    if (before === undefined) {
      changes.push({ type: "added", server: name, new: after });
    } else if (after === undefined) {
      changes.push({ type: "removed", server: name, old: before });
    } else if (JSON.stringify(before) !== JSON.stringify(after)) {
      changes.push({ type: "modified", server: name, old: before, new: after });
    }
  }
  return changes;
}

function countHooks(cfg: RecordShape): number {
  const hooks = safeRecord(cfg.hooks);
  let total = 0;
  for (const entries of Object.values(hooks)) {
    for (const entry of safeList(entries)) {
      if (entry && typeof entry === "object" && !Array.isArray(entry)) {
        const nested = safeList((entry as RecordShape).hooks);
        total += nested.length || 1;
      } else {
        total += 1;
      }
    }
  }
  return total;
}

function collectHookChanges(oldCfg: RecordShape, newCfg: RecordShape) {
  const oldHooks = safeRecord(oldCfg.hooks);
  const newHooks = safeRecord(newCfg.hooks);
  const oldEvents = Object.keys(oldHooks);
  const newEvents = Object.keys(newHooks);
  return {
    old_hook_count: countHooks(oldCfg),
    new_hook_count: countHooks(newCfg),
    removed_events: oldEvents.filter((event) => !newEvents.includes(event)).sort(),
    added_events: newEvents.filter((event) => !oldEvents.includes(event)).sort(),
    modified_events: oldEvents
      .filter((event) => newEvents.includes(event) && JSON.stringify(oldHooks[event]) !== JSON.stringify(newHooks[event]))
      .sort()
  };
}

function collectEnvChanges(oldCfg: RecordShape, newCfg: RecordShape) {
  const oldEnv = safeRecord(oldCfg.env);
  const newEnv = safeRecord(newCfg.env);
  const keys = new Set([...Object.keys(oldEnv), ...Object.keys(newEnv)]);
  return [...keys]
    .sort()
    .flatMap((key) =>
      JSON.stringify(oldEnv[key]) === JSON.stringify(newEnv[key]) ? [] : [{ key, old: oldEnv[key], new: newEnv[key] }]
    );
}

function scoreToVerdict(score: number) {
  if (score >= 80) {
    return { verdict: "deny", risk_level: "critical" };
  }
  if (score >= 45) {
    return { verdict: "ask", risk_level: "high" };
  }
  if (score >= 20) {
    return { verdict: "ask", risk_level: "med" };
  }
  return { verdict: "allow", risk_level: "low" };
}

export function reviewConfigChange(filePath: string, oldConfig: RecordShape = {}, newConfig: RecordShape = {}) {
  const reasons: string[] = [];
  const controls: string[] = [];
  let risk_score = 0;

  const oldAllow = new Set(safeList(safeRecord(oldConfig.permissions).allow).map(String));
  const newAllow = new Set(safeList(safeRecord(newConfig.permissions).allow).map(String));
  for (const pattern of ["Bash(rm:*)", "Bash(sudo:*)", "Bash(curl:*)", "Bash(wget:*)", "Bash(ssh:*)"]) {
    if (!oldAllow.has(pattern) && newAllow.has(pattern)) {
      risk_score += 80;
      reasons.push(`Dangerous allow pattern added: ${pattern}`);
      controls.push("manual-trust-review", "deny-by-default");
    }
  }

  const mcp_changes = collectMcpChanges(oldConfig, newConfig);
  for (const change of mcp_changes) {
    if (change.type === "added") {
      risk_score += 30;
      reasons.push(`New MCP server added: ${change.server}`);
      controls.push("mcp-endpoint-review");
    } else if (change.type === "modified") {
      risk_score += 35;
      reasons.push(`MCP server modified: ${change.server}`);
      controls.push("mcp-diff-review");
    }
  }

  const hook_changes = collectHookChanges(oldConfig, newConfig);
  if (hook_changes.new_hook_count < Math.max(1, hook_changes.old_hook_count - 2)) {
    risk_score += 35;
    reasons.push(`Hook count reduced significantly (${hook_changes.old_hook_count} -> ${hook_changes.new_hook_count})`);
    controls.push("require-hook-audit");
  }
  if (hook_changes.removed_events.length > 0) {
    risk_score += 25;
    reasons.push(`Hook events removed: ${hook_changes.removed_events.join(", ")}`);
    controls.push("event-removal-review");
  }
  if (hook_changes.modified_events.length > 0) {
    risk_score += 20;
    reasons.push(`Hook definitions modified: ${hook_changes.modified_events.join(", ")}`);
    controls.push("hook-diff-review");
  }

  const env_changes = collectEnvChanges(oldConfig, newConfig);
  for (const change of env_changes) {
    if (String(change.key).match(/key|token|secret|password|credential/i)) {
      risk_score += 20;
      reasons.push(`Sensitive environment key modified: ${change.key}`);
      controls.push("secret-env-review");
    } else {
      risk_score += 5;
      reasons.push(`Environment key modified: ${change.key}`);
    }
  }

  return {
    ts: new Date().toISOString(),
    changed_files: filePath ? [filePath] : [],
    mcp_changes,
    hook_changes,
    env_changes,
    risk_score,
    ...scoreToVerdict(risk_score),
    reasons,
    controls: [...new Set(controls)].sort()
  };
}

export function writeTrustManifest(projectDir: string, review: RecordShape): string {
  const trustDir = join(projectDir, ".omg", "trust");
  ensureDir(trustDir);
  const manifestPath = join(trustDir, "manifest.lock.json");
  const payload: RecordShape = {
    version: "omg-v2-bun",
    updated_at: new Date().toISOString(),
    last_review: review
  };
  const digest = createHash("sha256")
    .update(JSON.stringify(payload, Object.keys(payload).sort()))
    .digest("hex");
  payload.signature = digest;
  writeJsonFile(manifestPath, payload);
  return manifestPath;
}
