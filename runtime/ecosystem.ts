import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ensureDir, nowIso } from "./common.ts";

export const DEFAULT_ECOSYSTEM_REPO_DIR = ".omg/ecosystem/repos";
export const DEFAULT_ECOSYSTEM_LOCK_PATH = ".omg/state/ecosystem-lock.json";

type EcosystemRepo = {
  name: string;
  aliases: string[];
  repo: string;
  ref: string;
  route: string;
  category: string;
  capabilities: string[];
  notes: string;
};

const ECOSYSTEM_REPOS: EcosystemRepo[] = [
  {
    name: "omg-superpowers",
    aliases: ["omg-superpowers"],
    repo: "https://github.com/trac3er00/OMG.git",
    ref: "main",
    route: "plan",
    category: "tdd",
    capabilities: ["tdd", "planning", "execution"],
    notes: "Strict execution and verification patterns."
  },
  {
    name: "ralph-wiggum",
    aliases: ["ralph-wiggum", "ralph"],
    repo: "https://github.com/anthropics/claude-code.git",
    ref: "main",
    route: "runtime_ship",
    category: "persistent-loop",
    capabilities: ["persistent-mode", "completion-promises", "iteration"],
    notes: "Persistent loop patterns."
  },
  {
    name: "claude-flow",
    aliases: ["claude-flow"],
    repo: "https://github.com/ruvnet/claude-flow.git",
    ref: "main",
    route: "ccg",
    category: "orchestration",
    capabilities: ["multi-agent", "coordination", "task-routing"],
    notes: "CCG orchestration ideas."
  },
  {
    name: "claude-mem",
    aliases: ["claude-mem"],
    repo: "https://github.com/thedotmack/claude-mem.git",
    ref: "main",
    route: "memory",
    category: "memory",
    capabilities: ["session-memory", "knowledge-capture", "recall"],
    notes: "Memory workflows."
  },
  {
    name: "memsearch",
    aliases: ["memsearch", "memory-search"],
    repo: "https://github.com/rjyo/memory-search.git",
    ref: "main",
    route: "memory",
    category: "memory-search",
    capabilities: ["semantic-search", "retrieval", "indexing"],
    notes: "Focused memory retrieval."
  },
  {
    name: "beads",
    aliases: ["beads"],
    repo: "https://github.com/steveyegge/beads.git",
    ref: "main",
    route: "maintainer",
    category: "context-engineering",
    capabilities: ["context", "workflow", "agent-patterns"],
    notes: "Context engineering."
  },
  {
    name: "planning-with-files",
    aliases: ["planning-with-files", "planning with files"],
    repo: "https://github.com/OthmanAdi/planning-with-files.git",
    ref: "master",
    route: "plan",
    category: "planning",
    capabilities: ["file-based-plans", "checklists", "handoff"],
    notes: "Plan artifacts."
  },
  {
    name: "hooks-mastery",
    aliases: ["hooks-mastery"],
    repo: "https://github.com/disler/claude-code-hooks-mastery.git",
    ref: "main",
    route: "health",
    category: "hooks",
    capabilities: ["hook-design", "hook-hardening", "hook-automation"],
    notes: "Hook hardening references."
  },
  {
    name: "compound-engineering",
    aliases: ["compound-engineering", "compounding-engineering"],
    repo: "https://github.com/EveryInc/compounding-engineering-plugin.git",
    ref: "main",
    route: "ccg",
    category: "compound-workflows",
    capabilities: ["iterative-improvement", "compound-results", "workflow-composition"],
    notes: "Compound workflows."
  }
];

function canonical(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, "-");
}

export function listEcosystemRepos(): EcosystemRepo[] {
  return ECOSYSTEM_REPOS.map((repo) => ({ ...repo, aliases: [...repo.aliases], capabilities: [...repo.capabilities] }));
}

export function ecosystemStatus(options: { project_dir: string }) {
  const repos = listEcosystemRepos().map((repo) => {
    const repoDir = join(options.project_dir, DEFAULT_ECOSYSTEM_REPO_DIR, repo.name);
    return {
      ...repo,
      repo_segments: [".omg", "ecosystem", "repos", repo.name],
      installed: existsSync(repoDir),
      path: repoDir
    };
  });
  return {
    schema: "OmgEcosystemStatus",
    status: "ok",
    generated_at: nowIso(),
    repos
  };
}

export function syncEcosystemRepos(options: {
  project_dir: string;
  names?: string[];
  update?: boolean;
  depth?: number;
}) {
  const requested = options.names || [];
  const selected = requested.length
    ? requested
    : ECOSYSTEM_REPOS.map((repo) => repo.name);
  const lockPath = join(options.project_dir, DEFAULT_ECOSYSTEM_LOCK_PATH);
  const unknown: string[] = [];
  const entries: Record<string, unknown>[] = [];
  const lockData = existsSync(lockPath) ? JSON.parse(readFileSync(lockPath, "utf8")) : {};

  ensureDir(join(options.project_dir, ".omg", "ecosystem", "repos"));
  ensureDir(join(options.project_dir, ".omg", "state"));

  for (const raw of selected) {
    const repo = ECOSYSTEM_REPOS.find((candidate) => canonical(candidate.name) === canonical(raw) || candidate.aliases.some((alias) => canonical(alias) === canonical(raw)));
    if (!repo) {
      unknown.push(raw);
      continue;
    }
    const repoDir = join(options.project_dir, DEFAULT_ECOSYSTEM_REPO_DIR, repo.name);
    ensureDir(repoDir);
    entries.push({
      status: "ok",
      name: repo.name,
      action: existsSync(join(repoDir, ".git")) ? (options.update ? "updated" : "cached") : "prepared",
      repo_segments: [".omg", "ecosystem", "repos", repo.name],
      path: repoDir
    });
    (lockData as Record<string, unknown>)[repo.name] = {
      repo: repo.repo,
      ref: repo.ref,
      synced_at: nowIso()
    };
  }

  writeFileSync(lockPath, `${JSON.stringify(lockData, null, 2)}\n`, "utf8");
  return {
    schema: "OmgEcosystemSync",
    status: "ok",
    generated_at: nowIso(),
    unknown,
    entries
  };
}
