#!/usr/bin/env node
/**
 * OAL HUD — Standalone statusline for Claude Code.
 *
 * Supports legacy OMC HUD options from ~/.claude/settings.json via `omcHud`
 * and native options via `oalHud`.
 */

import { readFileSync, existsSync, readdirSync, realpathSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { execFileSync } from "node:child_process";

// ── ANSI helpers ────────────────────────────────────────────────────────────
const ESC = "\x1b[";
const bold = (t) => `${ESC}1m${t}${ESC}0m`;
const dim = (t) => `${ESC}2m${t}${ESC}0m`;
const green = (t) => `${ESC}32m${t}${ESC}0m`;
const yellow = (t) => `${ESC}33m${t}${ESC}0m`;
const red = (t) => `${ESC}31m${t}${ESC}0m`;
const magenta = (t) => `${ESC}35m${t}${ESC}0m`;
const cyan = (t) => `${ESC}36m${t}${ESC}0m`;

function readOalVersion() {
  const scriptPath = realpathSync(fileURLToPath(import.meta.url));
  const scriptDir = dirname(scriptPath);

  try {
    const pluginJsonPath = join(scriptDir, "..", ".claude-plugin", "plugin.json");
    const pluginJson = JSON.parse(readFileSync(pluginJsonPath, "utf8"));
    if (typeof pluginJson?.version === "string" && pluginJson.version.trim()) {
      return pluginJson.version.trim();
    }
  } catch {
    // fall through to git tag fallback
  }

  try {
    const rootDir = join(scriptDir, "..");
    const latestTag = execFileSync("git", ["describe", "--tags", "--abbrev=0"], {
      cwd: rootDir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    const normalized = latestTag.replace(/^v/, "").trim();
    if (normalized) return normalized;
  } catch {
    // fall through to static fallback
  }

  return "1.0.1";
}

const OAL_VERSION = readOalVersion();

const DEFAULT_HUD_CONFIG = {
  preset: "focused",
  elements: {
    cwd: true,
    cwdFormat: "relative",
    gitRepo: false,
    gitBranch: false,
    model: false,
    modelFormat: "short",
    omcLabel: true,
    rateLimits: true,
    promptTime: true,
    sessionHealth: true,
    contextBar: true,
    activeSkills: true,
    lastSkill: true,
    showCallCounts: false,
    ralph: true,
    autopilot: true,
    prdStory: true,
    agents: true,
    agentsFormat: "count",
    backgroundTasks: true,
    todos: true,
    thinking: true,
    thinkingFormat: "text",
    permissionStatus: false,
    useBars: false,
    maxOutputLines: 4,
    safeMode: true,
    inventory: true,
  },
  thresholds: {
    contextWarning: 70,
    contextCompactSuggestion: 80,
    contextCritical: 85,
    ralphWarning: 7,
  },
  contextLimitWarning: {
    threshold: 80,
    autoCompact: false,
  },
};

const PRESET_CONFIGS = {
  minimal: {
    cwd: true,
    cwdFormat: "folder",
    gitRepo: false,
    gitBranch: false,
    model: false,
    modelFormat: "short",
    omcLabel: true,
    rateLimits: true,
    activeSkills: true,
    lastSkill: true,
    contextBar: false,
    promptTime: false,
    sessionHealth: false,
    ralph: true,
    autopilot: true,
    prdStory: false,
    agents: true,
    agentsFormat: "count",
    backgroundTasks: false,
    todos: true,
    thinking: false,
    thinkingFormat: "text",
    permissionStatus: false,
    useBars: false,
    showCallCounts: false,
    maxOutputLines: 2,
    safeMode: true,
    inventory: true,
  },
  focused: {
    cwd: true,
    cwdFormat: "relative",
    gitRepo: false,
    gitBranch: true,
    model: false,
    modelFormat: "short",
    omcLabel: true,
    rateLimits: true,
    activeSkills: true,
    lastSkill: true,
    contextBar: true,
    promptTime: true,
    sessionHealth: true,
    ralph: true,
    autopilot: true,
    prdStory: true,
    agents: true,
    agentsFormat: "count",
    backgroundTasks: true,
    todos: true,
    thinking: true,
    thinkingFormat: "text",
    permissionStatus: false,
    useBars: true,
    showCallCounts: false,
    maxOutputLines: 4,
    safeMode: true,
    inventory: true,
  },
  full: {
    cwd: true,
    cwdFormat: "relative",
    gitRepo: true,
    gitBranch: true,
    model: false,
    modelFormat: "short",
    omcLabel: true,
    rateLimits: true,
    activeSkills: true,
    lastSkill: true,
    contextBar: true,
    promptTime: true,
    sessionHealth: true,
    ralph: true,
    autopilot: true,
    prdStory: true,
    agents: true,
    agentsFormat: "count",
    backgroundTasks: true,
    todos: true,
    thinking: true,
    thinkingFormat: "text",
    permissionStatus: false,
    useBars: true,
    showCallCounts: false,
    maxOutputLines: 12,
    safeMode: true,
    inventory: true,
  },
  dense: {
    cwd: true,
    cwdFormat: "relative",
    gitRepo: true,
    gitBranch: true,
    model: false,
    modelFormat: "short",
    omcLabel: true,
    rateLimits: true,
    activeSkills: true,
    lastSkill: true,
    contextBar: true,
    promptTime: true,
    sessionHealth: true,
    ralph: true,
    autopilot: true,
    prdStory: true,
    agents: true,
    agentsFormat: "count",
    backgroundTasks: true,
    todos: true,
    thinking: true,
    thinkingFormat: "text",
    permissionStatus: false,
    useBars: true,
    showCallCounts: false,
    maxOutputLines: 6,
    safeMode: true,
    inventory: true,
  },
  opencode: {
    cwd: true,
    cwdFormat: "relative",
    gitRepo: false,
    gitBranch: true,
    model: false,
    modelFormat: "short",
    omcLabel: true,
    rateLimits: false,
    activeSkills: true,
    lastSkill: true,
    contextBar: true,
    promptTime: true,
    sessionHealth: true,
    ralph: true,
    autopilot: true,
    prdStory: false,
    agents: true,
    agentsFormat: "count",
    backgroundTasks: false,
    todos: true,
    thinking: true,
    thinkingFormat: "text",
    permissionStatus: false,
    useBars: false,
    showCallCounts: false,
    maxOutputLines: 4,
    safeMode: true,
    inventory: true,
  },
};

function countByExt(dirPath, ext) {
  if (!existsSync(dirPath)) return 0;
  try {
    return readdirSync(dirPath, { withFileTypes: true }).filter(
      (entry) => entry.isFile() && entry.name.endsWith(ext)
    ).length;
  } catch {
    return 0;
  }
}

function getRuntimeInventory() {
  const claudeDir = getClaudeConfigDir();
  return {
    agents: countByExt(join(claudeDir, "agents"), ".md"),
    hooks: countByExt(join(claudeDir, "hooks"), ".py"),
    commands: countByExt(join(claudeDir, "commands"), ".md"),
    rules: countByExt(join(claudeDir, "rules"), ".md"),
  };
}

function renderInventory(inv) {
  if (!inv) return null;
  return `\u{1F9F0}agents:${cyan(String(inv.agents))}`;
}

function parseModeToken(mode) {
  const raw = String(mode || "");
  const lower = raw.toLowerCase();
  const base = lower.split("#")[0].split(":")[0];
  const iterMatch = raw.match(/#(\d+)/);
  const iter = iterMatch ? iterMatch[1] : "";
  const phase = raw.includes(":") ? raw.split(":").slice(1).join(":") : "";
  return { base, iter, phase };
}

function renderModeBadge(mode) {
  const { base, iter, phase } = parseModeToken(mode);
  let key = base;
  let icon = "\u2699";
  let title = (base || "mode").toUpperCase();
  let colorFn = magenta;

  if (base === "ultrawork" || base === "ulw") {
    key = "ulw";
    icon = "\u26A1";
    title = "ULW";
    colorFn = yellow;
  } else if (base === "team" || base === "crazy") {
    key = "crazy";
    icon = "\u{1F92F}";
    title = "CRAZY";
    colorFn = red;
  } else if (base === "ralph") {
    key = "ralph";
    icon = "\u{1F9E0}";
    title = "RALPH";
    colorFn = green;
  } else if (base === "autopilot") {
    key = "autopilot";
    icon = "\u{1F6E0}";
    title = "AUTOPILOT";
    colorFn = cyan;
  }

  const extra = `${iter ? `#${iter}` : ""}${phase ? `:${phase}` : ""}`;
  return { key, text: colorFn(`${icon}${title}${extra}`) };
}

function renderModeBadges(modes, opts = {}) {
  if (!Array.isArray(modes) || modes.length === 0) return null;
  const hideRalph = !!opts.hideRalph;
  const hideAutopilot = !!opts.hideAutopilot;
  const seen = new Set();
  const badges = [];

  for (const mode of modes) {
    const badge = renderModeBadge(mode);
    if (hideRalph && badge.key === "ralph") continue;
    if (hideAutopilot && badge.key === "autopilot") continue;
    if (seen.has(badge.key)) continue;
    seen.add(badge.key);
    badges.push(badge.text);
  }

  if (badges.length === 0) return null;
  return badges.join("+");
}

function colorByPercent(value, label, warning = 60, critical = 85) {
  if (value >= critical) return red(`${label}`);
  if (value >= warning) return yellow(`${label}`);
  return green(`${label}`);
}

function readJsonSafe(path) {
  try {
    if (!existsSync(path)) return null;
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

function getClaudeConfigDir() {
  return process.env.CLAUDE_CONFIG_DIR || join(homedir(), ".claude");
}

function readRawHudConfig() {
  const claudeDir = getClaudeConfigDir();
  const settingsPath = join(claudeDir, "settings.json");
  const settings = readJsonSafe(settingsPath) || {};
  if (settings.oalHud) return settings.oalHud;
  if (settings.omcHud) return settings.omcHud;

  // OMC legacy HUD config fallback.
  const legacyPath = join(claudeDir, ".omc", "hud-config.json");
  return readJsonSafe(legacyPath) || {};
}

function readHudConfig() {
  const source = readRawHudConfig();
  const preset = source.preset || DEFAULT_HUD_CONFIG.preset;
  const presetElements = PRESET_CONFIGS[preset] || {};
  const elements = {
    ...DEFAULT_HUD_CONFIG.elements,
    ...presetElements,
    ...(source.elements || {}),
  };
  const thresholds = {
    ...DEFAULT_HUD_CONFIG.thresholds,
    ...(source.thresholds || {}),
  };
  const contextLimitWarning = {
    ...DEFAULT_HUD_CONFIG.contextLimitWarning,
    ...(source.contextLimitWarning || {}),
  };
  return { preset, elements, thresholds, contextLimitWarning };
}

async function readStdin() {
  if (process.stdin.isTTY) return null;
  const chunks = [];
  process.stdin.setEncoding("utf8");
  for await (const chunk of process.stdin) chunks.push(chunk);
  const raw = chunks.join("");
  if (!raw.trim()) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function getContextPercent(stdin) {
  let pct = stdin?.context_window?.used_percentage;
  if (typeof pct === "number" && !Number.isNaN(pct)) {
    if (pct > 0 && pct <= 1) pct *= 100;
    return Math.min(100, Math.max(0, Math.round(pct)));
  }
  const size = stdin?.context_window?.context_window_size;
  if (!size || size <= 0) return 0;
  const usage = stdin?.context_window?.current_usage ?? {};
  const tokens =
    (usage.input_tokens ?? 0) +
    (usage.cache_creation_input_tokens ?? 0) +
    (usage.cache_read_input_tokens ?? 0);
  return Math.min(100, Math.round((tokens / size) * 100));
}

function formatModelName(id, format) {
  if (!id) return "?";
  if (format === "full") return id;

  const lower = id.toLowerCase();
  let family = "";
  if (lower.includes("opus")) family = "opus";
  else if (lower.includes("sonnet")) family = "sonnet";
  else if (lower.includes("haiku")) family = "haiku";
  else family = id.split("/").pop()?.split("-")[0] || id;

  if (format !== "versioned") return family;

  const m = lower.match(/-(\d)-(\d)(?:-|$)/);
  if (m) {
    return `${family} ${m[1]}.${m[2]}`;
  }
  return family;
}

function getModelShort(stdin, format = "short") {
  const id = stdin?.model?.id ?? stdin?.model?.display_name ?? "";
  return formatModelName(id, format);
}

function sessionDuration(transcriptPath) {
  if (!transcriptPath || !existsSync(transcriptPath)) return null;
  try {
    const fd = readFileSync(transcriptPath, "utf8");
    const nlIdx = fd.indexOf("\n");
    const firstLine = fd.slice(0, nlIdx >= 0 ? nlIdx : Math.min(fd.length, 2000));
    if (!firstLine.trim()) return null;
    const first = JSON.parse(firstLine);
    const raw = first?.timestamp ?? first?.ts;
    if (!raw) return null;
    const start = new Date(raw);
    if (isNaN(start.getTime())) return null;
    const mins = Math.floor((Date.now() - start.getTime()) / 60_000);
    if (mins < 0 || mins > 10080) return null; // sanity: max 7 days
    return `${mins}m`;
  } catch {
    return null;
  }
}

function getGitInfo(cwd) {
  try {
    const root = execFileSync("git", ["-C", cwd, "rev-parse", "--show-toplevel"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    const branch = execFileSync("git", ["-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    return { repo: basename(root), branch };
  } catch {
    return { repo: null, branch: null };
  }
}

function renderCwd(cwd, format) {
  if (!cwd) return null;
  if (format === "absolute") return cwd;
  if (format === "folder") return basename(cwd);
  const home = homedir();
  if (cwd.startsWith(home)) return `~${cwd.slice(home.length) || "/"}`;
  return cwd;
}

function formatClock(iso) {
  try {
    const dt = new Date(iso);
    if (isNaN(dt.getTime())) return null;
    const hh = String(dt.getHours()).padStart(2, "0");
    const mm = String(dt.getMinutes()).padStart(2, "0");
    const ss = String(dt.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  } catch {
    return null;
  }
}

function renderBar(percent, width = 10) {
  const clamped = Math.max(0, Math.min(100, Number(percent) || 0));
  const filled = Math.round((clamped / 100) * width);
  return `[${"█".repeat(filled)}${"░".repeat(Math.max(0, width - filled))}]`;
}

function getLastPromptTime(cwd) {
  const candidates = [
    join(cwd, ".oal", "state", "hud-state.json"),
    join(cwd, ".omc", "state", "hud-state.json"),
    join(cwd, ".omc", "hud-state.json"),
  ];
  for (const p of candidates) {
    const state = readJsonSafe(p);
    if (state?.lastPromptTimestamp) {
      const t = formatClock(state.lastPromptTimestamp);
      if (t) return t;
    }
  }
  return null;
}

function readOalState(cwd) {
  const stateDir = join(cwd, ".oal", "state");
  const result = {
    modes: [],
    hookCount: 0,
    profile: null,
    ralph: null,
    autopilot: null,
    prd: null,
    backgroundTasks: [],
  };

  const modeFiles = [
    ["ralph", "ralph-state.json"],
    ["ultrawork", "ultrawork-state.json"],
    ["autopilot", "autopilot-state.json"],
    ["ultrapilot", "ultrapilot-state.json"],
    ["team", "team-state.json"],
    ["pipeline", "pipeline-state.json"],
    ["ultraqa", "ultraqa-state.json"],
  ];

  for (const [name, file] of modeFiles) {
    const state = readJsonSafe(join(stateDir, file));
    if (state?.active) {
      const iter = state.iteration ? `#${state.iteration}` : "";
      const phase = state.current_phase ? `:${state.current_phase}` : "";
      result.modes.push(`${name}${iter}${phase}`);
    }
  }

  const persistent = readJsonSafe(join(stateDir, "persistent-mode.json"));
  if (persistent?.status === "active" && persistent?.mode) {
    if (!result.modes.includes(persistent.mode)) {
      result.modes.push(String(persistent.mode));
    }
  }

  const ralphState = readJsonSafe(join(stateDir, "ralph-state.json"));
  if (ralphState?.active) {
    result.ralph = {
      active: true,
      iteration: ralphState.iteration || 0,
      maxIterations: ralphState.maxIterations || ralphState.max_iterations || 10,
    };
  }

  const autopilotState = readJsonSafe(join(stateDir, "autopilot-state.json"));
  if (autopilotState?.active) {
    result.autopilot = {
      active: true,
      phase: autopilotState.phase || autopilotState.current_phase || "execution",
      iteration: autopilotState.iteration || 1,
      maxIterations: autopilotState.maxIterations || autopilotState.max_iterations || 10,
      tasksCompleted: autopilotState.tasksCompleted || autopilotState.tasks_completed || 0,
      tasksTotal: autopilotState.tasksTotal || autopilotState.tasks_total || 0,
    };
  }

  const prdState = readJsonSafe(join(stateDir, "prd-state.json"));
  if (prdState) {
    result.prd = {
      currentStoryId: prdState.currentStoryId || prdState.current_story_id || null,
      completed: prdState.completed || 0,
      total: prdState.total || 0,
    };
  }

  const hudState = readJsonSafe(join(stateDir, "hud-state.json"));
  if (hudState?.backgroundTasks && Array.isArray(hudState.backgroundTasks)) {
    result.backgroundTasks = hudState.backgroundTasks.filter((t) => t.status === "running");
  }

  try {
    const yamlPath = join(stateDir, "profile.yaml");
    if (existsSync(yamlPath)) {
      const text = readFileSync(yamlPath, "utf8");
      const nameMatch = text.match(/^name:\s*["']?(.+?)["']?\s*$/m);
      if (nameMatch) result.profile = nameMatch[1];
    }
  } catch {
    // ignore
  }

  const ledger = join(stateDir, "ledger", "tool-ledger.jsonl");
  if (existsSync(ledger)) {
    try {
      const buf = readFileSync(ledger);
      let count = 0;
      for (let i = 0; i < buf.length; i++) {
        if (buf[i] === 10) count++;
      }
      if (buf.length > 0 && count === 0) count = 1;
      result.hookCount = count;
    } catch {
      // ignore
    }
  }
  return result;
}

function parseTranscript(transcriptPath) {
  const result = {
    tools: 0,
    agents: 0,
    skills: 0,
    runningAgentCount: 0,
    todos: [],
    lastSkill: null,
    thinkingActive: false,
    pendingPermission: null,
  };
  if (!transcriptPath || !existsSync(transcriptPath)) return result;
  try {
    const content = readFileSync(transcriptPath, "utf8");
    const lines = content.split("\n");
    const agentMap = new Map();
    const STALE_MS = 30 * 60 * 1000;
    let lastThinkingTs = 0;
    let pendingToolUse = null;
    const resolvedIds = new Set();

    const parseEpochMs = (raw) => {
      if (typeof raw === "number" && Number.isFinite(raw)) return raw;
      if (typeof raw !== "string" || raw.length === 0) return Date.now();
      const t = Date.parse(raw);
      return Number.isNaN(t) ? Date.now() : t;
    };

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line);
        const entryTs = parseEpochMs(entry.timestamp || entry.ts);

        if (entry.type === "assistant" && Array.isArray(entry.message?.content)) {
          for (const block of entry.message.content) {
            if (block.type === "thinking" || block.type === "reasoning") {
              lastThinkingTs = entryTs;
            }

            if (block.type === "tool_use") {
              const name = block.name || "";
              const input = block.input || {};
              const id = block.id || "";

              if (name === "Task" || name === "proxy_Task") {
                result.agents++;
                agentMap.set(id, {
                  type: input.agent_type || input.type || "unknown",
                  description: input.description || "",
                  startTime: entryTs,
                });
              } else if (name === "Skill" || name === "proxy_Skill") {
                result.skills++;
                const skillName = input.skill_name || input.name || "";
                if (skillName) {
                  result.lastSkill = skillName.split(":").pop() || skillName;
                }
              } else if (name === "TodoWrite" || name === "proxy_TodoWrite") {
                if (Array.isArray(input.todos)) {
                  result.todos = input.todos;
                }
              } else {
                result.tools++;
              }

              pendingToolUse = {
                id,
                toolName: name.replace(/^proxy_/, ""),
                target: input.command || input.filePath || input.path || "",
              };
            }
          }
        }

        if (entry.type === "tool" || entry.type === "tool_result") {
          const useId = entry.tool_use_id || entry.id || "";
          if (useId) {
            resolvedIds.add(useId);
            if (agentMap.has(useId)) {
              agentMap.delete(useId);
            }
            if (pendingToolUse && pendingToolUse.id === useId) {
              pendingToolUse = null;
            }
          }
        }
      } catch {
        // skip unparseable lines
      }
    }

    const now = Date.now();
    for (const [id, agent] of agentMap) {
      if (!resolvedIds.has(id) && now - agent.startTime < STALE_MS) {
        result.runningAgentCount++;
      }
    }

    result.thinkingActive = lastThinkingTs > 0;

    if (pendingToolUse && !resolvedIds.has(pendingToolUse.id)) {
      result.pendingPermission = {
        toolName: pendingToolUse.toolName,
        targetSummary: pendingToolUse.target ? String(pendingToolUse.target).slice(0, 40) : "",
      };
    }
  } catch {
    // ignore read errors
  }
  return result;
}

function renderRalph(ralph, thresholds) {
  if (!ralph?.active) return null;
  const { iteration, maxIterations } = ralph;
  const ralphWarn = thresholds?.ralphWarning ?? 7;
  const criticalThreshold = Math.floor(maxIterations * 0.9);
  let colorFn = green;
  if (iteration >= criticalThreshold) colorFn = red;
  else if (iteration >= ralphWarn) colorFn = yellow;
  return `ralph:${colorFn(`${iteration}/${maxIterations}`)}`;
}

function renderAutopilot(autopilot) {
  if (!autopilot?.active) return null;
  const phaseNames = {
    expansion: "Expand",
    planning: "Plan",
    execution: "Build",
    qa: "QA",
    validation: "Verify",
    complete: "Done",
    failed: "Failed",
  };
  const phaseIndex = { expansion: 1, planning: 2, execution: 3, qa: 4, validation: 5, complete: 5, failed: 0 };
  const { phase, tasksCompleted, tasksTotal } = autopilot;
  const phaseNum = phaseIndex[phase] || 0;
  const phaseName = phaseNames[phase] || phase;
  let phaseColor = cyan;
  if (phase === "complete") phaseColor = green;
  else if (phase === "failed") phaseColor = red;
  else if (phase === "qa") phaseColor = yellow;
  else if (phase === "validation") phaseColor = magenta;
  let output = `${cyan("[AUTOPILOT]")} Phase ${phaseColor(`${phaseNum}/5`)}: ${phaseName}`;
  if (phase === "execution" && tasksTotal > 0) {
    const taskColor = tasksCompleted === tasksTotal ? green : yellow;
    output += ` | Tasks: ${taskColor(`${tasksCompleted || 0}/${tasksTotal}`)}`;
  }
  return output;
}

function renderLastSkill(skillName) {
  if (!skillName) return null;
  return cyan(`skill:${skillName}`);
}

function renderThinking(active, format) {
  if (!active) return null;
  switch (format) {
    case "bubble":
      return "\u{1F4AD}";
    case "brain":
      return "\u{1F9E0}";
    case "face":
      return "\u{1F914}";
    case "text":
    default:
      return cyan("thinking");
  }
}

function renderRunningAgents(count) {
  if (count <= 0) return null;
  return `agents:${cyan(String(count))}`;
}

function renderBackgroundTasks(tasks) {
  if (!tasks || tasks.length === 0) return null;
  const running = tasks.length;
  const MAX = 5;
  let colorFn = green;
  if (running >= MAX) colorFn = yellow;
  else if (running >= MAX - 1) colorFn = cyan;
  return `bg:${colorFn(`${running}/${MAX}`)}`;
}

function renderTodos(todos) {
  if (!todos || todos.length === 0) return null;
  const completed = todos.filter((t) => t.status === "completed").length;
  const total = todos.length;
  const pct = (completed / total) * 100;
  let colorFn = cyan;
  if (pct >= 80) colorFn = green;
  else if (pct >= 50) colorFn = yellow;
  const inProgress = todos.find((t) => t.status === "in_progress");
  let result = `todos:${colorFn(`${completed}/${total}`)}`;
  if (inProgress) {
    const desc = (inProgress.content || "...").slice(0, 30);
    result += ` ${dim(`(working: ${desc})`)}`;
  }
  return result;
}

function renderPermission(pending) {
  if (!pending) return null;
  return `${yellow("APPROVE?")} ${dim(pending.toolName.toLowerCase())}:${pending.targetSummary}`;
}

function renderPrd(prd) {
  if (!prd) return null;
  const { currentStoryId, completed, total } = prd;
  if (total > 0 && completed === total) return green("PRD:done");
  if (currentStoryId) {
    const progress = total > 0 ? ` ${dim(`(${completed}/${total})`)}` : "";
    return `${cyan(currentStoryId)}${progress}`;
  }
  if (total > 0) return dim(`PRD:${completed}/${total}`);
  return null;
}

function readRateLimits() {
  const claudeDir = getClaudeConfigDir();
  const cachePaths = [
    join(claudeDir, "oal-runtime", ".usage-cache.json"),
    join(claudeDir, "plugins", "oh-my-claudecode", ".usage-cache.json"),
    join(claudeDir, ".oal", "usage-cache.json"),
    join(homedir(), ".oal", "usage-cache.json"),
  ];
  for (const p of cachePaths) {
    const raw = readJsonSafe(p);
    if (!raw) continue;
    // Handle wrapped format: { timestamp, data, source }
    const data = raw.data ?? raw;
    if (data.hourly || data.daily || data.weekly) return data;
    if (typeof data.fiveHourPercent === "number" || typeof data.weeklyPercent === "number") return data;
  }
  return null;
}

function toNumberOrZero(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function getSessionTokenTotal(stdin) {
  const usage = stdin?.context_window?.current_usage ?? {};
  const input = toNumberOrZero(usage.input_tokens);
  const output = toNumberOrZero(usage.output_tokens);
  const cacheCreation = toNumberOrZero(usage.cache_creation_input_tokens);
  const cacheRead = toNumberOrZero(usage.cache_read_input_tokens);
  const total = input + output + cacheCreation + cacheRead;
  return total > 0 ? total : null;
}

function formatDateKeyLocal(date) {
  const y = String(date.getFullYear());
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatDateKeyUtc(date) {
  const y = String(date.getUTCFullYear());
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function getDateKeysForLastDays(days) {
  const keys = new Set();
  const now = new Date();
  for (let i = 0; i < days; i++) {
    const day = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    keys.add(formatDateKeyLocal(day));
    keys.add(formatDateKeyUtc(day));
  }
  return keys;
}

function getStatsDailyModelTokens() {
  const claudeDir = getClaudeConfigDir();
  const statsPath = join(claudeDir, "stats-cache.json");
  const stats = readJsonSafe(statsPath);
  if (!stats || !Array.isArray(stats.dailyModelTokens)) return [];
  return stats.dailyModelTokens;
}

function sumTokensByDateKeys(rows, dateKeys) {
  let total = 0;
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const dateKey = typeof row.date === "string" ? row.date : null;
    if (!dateKey || !dateKeys.has(dateKey)) continue;

    const tokensByModel = row.tokensByModel;
    if (!tokensByModel || typeof tokensByModel !== "object") continue;
    for (const value of Object.values(tokensByModel)) {
      total += toNumberOrZero(value);
    }
  }
  return total > 0 ? total : null;
}

function getDailyTokenTotalFromStatsCache() {
  const rows = getStatsDailyModelTokens();
  if (rows.length === 0) return null;
  const today = new Date();
  const keys = new Set([formatDateKeyLocal(today), formatDateKeyUtc(today)]);
  return sumTokensByDateKeys(rows, keys);
}

function getWeeklyTokenTotalFromStatsCache() {
  const rows = getStatsDailyModelTokens();
  if (rows.length === 0) return null;
  const keys = getDateKeysForLastDays(7);
  return sumTokensByDateKeys(rows, keys);
}

function formatTokenCount(value) {
  const n = Math.max(0, Math.round(Number(value) || 0));
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function renderTokenUsageTotals(sessionTotal, dailyTotal, weeklyTotal) {
  // Only show token counts when we have actual data from stats-cache
  // Rate limits (session: X%; weekly: Y%) are shown separately by renderRateLimits
  const parts = [];
  if (typeof sessionTotal === "number" && sessionTotal > 0) {
    parts.push(`session:${green(formatTokenCount(sessionTotal))}`);
  }
  if (typeof dailyTotal === "number" && dailyTotal > 0) {
    parts.push(`daily:${green(formatTokenCount(dailyTotal))}`);
  }
  if (typeof weeklyTotal === "number" && weeklyTotal > 0) {
    parts.push(`weekly:${green(formatTokenCount(weeklyTotal))}`);
  }
  return parts.length > 0 ? parts.join("; ") : null;
}

function formatResetTime(dateStr) {
  if (!dateStr) return null;
  const resetMs = new Date(dateStr).getTime();
  const diffMs = resetMs - Date.now();
  if (diffMs <= 0 || isNaN(diffMs)) return null;
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays > 0) {
    return `${diffDays}d${diffHours % 24}h`;
  }
  return `${diffHours}h${diffMinutes % 60}m`;
}

function renderRateLimits(limits) {
  if (!limits) return null;
  let sessionPart = null;
  let weeklyPart = null;

  // Session token limit (5-hour rolling window)
  if (limits.hourly) {
    const h = limits.hourly;
    const pct = h.limit > 0 ? Math.round((1 - h.remaining / h.limit) * 100) : 0;
    const safePct = Math.min(100, Math.max(0, pct));
    const leftPct = Math.max(0, 100 - safePct);
    const reset = formatResetTime(h.resetsAt);
    const resetPart = reset ? dim(` (${reset})`) : "";
    sessionPart = `session:${green(`${leftPct}%`)}${resetPart}`;
  } else if (typeof limits.fiveHourPercent === "number") {
    const p = Math.min(100, Math.max(0, Math.round(limits.fiveHourPercent)));
    const leftPct = Math.max(0, 100 - p);
    const reset = formatResetTime(limits.fiveHourResetsAt);
    const resetPart = reset ? dim(` (${reset})`) : "";
    sessionPart = `session:${green(`${leftPct}%`)}${resetPart}`;
  }

  // Weekly token limit
  if (limits.weekly) {
    const w = limits.weekly;
    const pct = w.limit > 0 ? Math.round((1 - w.remaining / w.limit) * 100) : 0;
    const safePct = Math.min(100, Math.max(0, pct));
    const leftPct = Math.max(0, 100 - safePct);
    const reset = formatResetTime(w.resetsAt);
    const resetPart = reset ? dim(` (${reset})`) : "";
    weeklyPart = `weekly:${green(`${leftPct}%`)}${resetPart}`;
  } else if (typeof limits.weeklyPercent === "number") {
    const p = Math.min(100, Math.max(0, Math.round(limits.weeklyPercent)));
    const leftPct = Math.max(0, 100 - p);
    const reset = formatResetTime(limits.weeklyResetsAt);
    const resetPart = reset ? dim(` (${reset})`) : "";
    weeklyPart = `weekly:${green(`${leftPct}%`)}${resetPart}`;
  }
  if (sessionPart && weeklyPart) return `${sessionPart}; ${weeklyPart}`;
  return sessionPart || weeklyPart;
}

function toSafeText(text) {
  return String(text)
    .replace(/\x1b\[[0-9;]*m/g, "")
    .replace(/⚠/g, "WARN");
}

function limitOutputLines(lines, maxLines) {
  const limit = Math.max(1, Number(maxLines) || DEFAULT_HUD_CONFIG.elements.maxOutputLines);
  return lines.slice(0, limit);
}

async function main() {
  try {
    const stdin = await readStdin();
    if (!stdin) {
      console.log(`${bold("[OAL]")} waiting...`);
      return;
    }

    const cfg = readHudConfig();
    const cwd = stdin.cwd || process.cwd();
    const ctxPct = getContextPercent(stdin);
    const model = getModelShort(stdin, cfg.elements.modelFormat || "short");
    const duration = sessionDuration(stdin.transcript_path);
    const oalState = readOalState(cwd);
    const transcript = parseTranscript(stdin.transcript_path);
    const rateLimits = readRateLimits();
    const sessionTokenTotal = getSessionTokenTotal(stdin);
    const dailyTokenTotal = getDailyTokenTotalFromStatsCache();
    const weeklyTokenTotal = getWeeklyTokenTotalFromStatsCache();
    const git = getGitInfo(cwd);
    const promptTime = getLastPromptTime(cwd);
    const inventory = getRuntimeInventory();

    const warning = Number(cfg.thresholds.contextWarning ?? 60);
    const critical = Number(cfg.thresholds.contextCritical ?? 85);
    const compactThreshold = Number(
      cfg.contextLimitWarning.threshold ?? cfg.thresholds.contextCompactSuggestion ?? 80
    );

    const els = [];

    // Git info (optional, on same line in OAL)
    if (cfg.elements.cwd) {
      const cwdText = renderCwd(cwd, cfg.elements.cwdFormat || "relative");
      if (cwdText) els.push(`\u{1F4C1}${dim("dir:")}${dim(cwdText)}`);
    }
    if (cfg.elements.gitRepo && git.repo) {
      els.push(dim(git.repo));
    }
    if (cfg.elements.gitBranch && git.branch) {
      els.push(dim(git.branch));
    }

    // [OAL#X.Y.Z] label
    if (cfg.elements.omcLabel !== false) {
      els.push(bold(`[OAL#${OAL_VERSION}]`));
    }

    // Rate limits
    if (cfg.elements.rateLimits !== false) {
      const rl = renderRateLimits(rateLimits);
      if (rl) els.push(rl);
    }

    const totals = renderTokenUsageTotals(sessionTokenTotal, dailyTokenTotal, weeklyTokenTotal);
    if (totals) els.push(totals);

    // Permission status (disabled by default)
    if (cfg.elements.permissionStatus && transcript.pendingPermission) {
      const perm = renderPermission(transcript.pendingPermission);
      if (perm) els.push(perm);
    }

    // Thinking indicator
    if (cfg.elements.thinking && transcript.thinkingActive) {
      const think = renderThinking(true, cfg.elements.thinkingFormat || "text");
      if (think) els.push(think);
    }

    // Prompt time
    if (cfg.elements.promptTime && promptTime) {
      els.push(`prompt:${green(promptTime)}`);
    }

    // Session duration
    if (cfg.elements.sessionHealth !== false && duration) {
      els.push(`session:${green(duration)}`);
    }

    // Ralph (rich format)
    if (cfg.elements.ralph !== false && oalState.ralph) {
      const ralphEl = renderRalph(oalState.ralph, cfg.thresholds);
      if (ralphEl) els.push(ralphEl);
    }

    // Autopilot (rich format)
    if (cfg.elements.autopilot !== false && oalState.autopilot) {
      const apEl = renderAutopilot(oalState.autopilot);
      if (apEl) els.push(apEl);
    }

    // PRD story
    if (cfg.elements.prdStory && oalState.prd) {
      const prdEl = renderPrd(oalState.prd);
      if (prdEl) els.push(prdEl);
    }

    // Active skills (modes) + last skill
    if (cfg.elements.activeSkills !== false) {
      const modeBadges = renderModeBadges(oalState.modes, {
        hideRalph: !!oalState.ralph,
        hideAutopilot: !!oalState.autopilot,
      });
      if (modeBadges) els.push(modeBadges);
      // Last skill from transcript
      if (cfg.elements.lastSkill !== false && transcript.lastSkill) {
        // Don't show if skill name matches an active mode
        if (!oalState.modes.some((m) => m.startsWith(transcript.lastSkill))) {
          const skillEl = renderLastSkill(transcript.lastSkill);
          if (skillEl) els.push(skillEl);
        }
      }
    } else if (cfg.elements.lastSkill !== false && transcript.lastSkill) {
      const skillEl = renderLastSkill(transcript.lastSkill);
      if (skillEl) els.push(skillEl);
    }

    // Context bar
    if (cfg.elements.contextBar !== false) {
      let suffix = "";
      if (ctxPct >= critical) suffix = " CRITICAL";
      else if (ctxPct >= compactThreshold) suffix = " COMPRESS?";
      const ctxLabel = cfg.elements.useBars ? `${renderBar(ctxPct)} ${ctxPct}%${suffix}` : `${ctxPct}%${suffix}`;
      els.push(`\u{1F9E0}context:${colorByPercent(ctxPct, ctxLabel, warning, critical)}`);
    }

    // Active agents
    if (cfg.elements.agents !== false) {
      const agentsEl = renderRunningAgents(transcript.runningAgentCount);
      if (agentsEl) els.push(agentsEl);
    }

    // Runtime inventory (installed components)
    if (cfg.elements.inventory !== false) {
      const invEl = renderInventory(inventory);
      if (invEl) els.push(invEl);
    }

    // Background tasks
    if (cfg.elements.backgroundTasks) {
      const bgEl = renderBackgroundTasks(oalState.backgroundTasks);
      if (bgEl) els.push(bgEl);
    }

    // Model name
    if (cfg.elements.model !== false && model && model !== "?") {
      els.push(dim(model));
    }

    const details = [];
    if (ctxPct >= compactThreshold) {
      details.push(red(`  ⚠ context at ${ctxPct}% — consider /compact`));
    }
    // Todos detail line
    if (cfg.elements.todos) {
      const todosEl = renderTodos(transcript.todos);
      if (todosEl) details.push(`  ${todosEl}`);
    }

    const sep = dim(" | ");
    const lines = [els.join(sep), ...details];
    const safeMode = cfg.elements.safeMode !== false;
    const finalLines = limitOutputLines(lines, cfg.elements.maxOutputLines).map((line) =>
      safeMode ? toSafeText(line) : line
    );
    console.log(finalLines.join("\n"));
  } catch (err) {
    console.log(`${bold("[OAL]")} HUD error`);
    console.error("[OAL HUD Error]", err instanceof Error ? err.message : err);
  }
}

main();
