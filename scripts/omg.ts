#!/usr/bin/env bun
import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  ensureParent,
  ensureProjectDir,
  nowRunId,
  parseSimpleIdeaYaml,
  printJson,
  readJsonFile,
  relativeToProject
} from "../runtime/common.ts";
import { dispatchRuntime } from "../runtime/dispatcher.ts";
import {
  DEFAULT_CONTRACT_SNAPSHOT_PATH,
  DEFAULT_GAP_REPORT_PATH,
  buildCompatGapReport,
  buildContractSnapshotPayload,
  dispatchCompatSkill,
  getCompatSkillContract,
  listCompatSkillContracts,
  listCompatSkills
} from "../runtime/compat.ts";
import { listEcosystemRepos, ecosystemStatus, syncEcosystemRepos } from "../runtime/ecosystem.ts";
import { dispatchTeam, executeCcgMode, executeCrazyMode } from "../runtime/team_router.ts";
import { evaluateBashCommand } from "../hooks/policy_engine.ts";
import { createEvidencePack } from "../hooks/shadow_manager.ts";
import { reviewConfigChange, writeTrustManifest } from "../hooks/trust_review.ts";
import { collectProviderStatusWithOptions, repairProviderHosts } from "../runtime/provider_bootstrap.ts";
import { runProviderSmokeMatrix } from "../runtime/provider_smoke.ts";
import { collectReleaseReadiness } from "../runtime/release_readiness.ts";

function loadJson(path: string): Record<string, unknown> {
  return readJsonFile<Record<string, unknown>>(path, {});
}

function loadIdea(pathOrJson: string, isInlineJson = false): Record<string, unknown> {
  if (isInlineJson) {
    return JSON.parse(pathOrJson) as Record<string, unknown>;
  }
  if (pathOrJson.endsWith(".yml") || pathOrJson.endsWith(".yaml")) {
    return parseSimpleIdeaYaml(pathOrJson) as unknown as Record<string, unknown>;
  }
  return loadJson(pathOrJson);
}

function usage(): never {
  const text = `OMG Bun CLI

Usage:
  omg ship --runtime <claude|gpt|local> --idea <path>
  omg fix --issue <id> [--runtime <runtime>]
  omg secure --command "<bash>"
  omg maintainer [--mode <triage|release|review|impact>]
  omg trust review --old <path> --new <path> [--file settings.json]
  omg runtime dispatch --runtime <claude|gpt|local> [--idea <path> | --idea-json <json>]
  omg teams --problem <text> [--target auto|codex|gemini|ccg]
  omg ccg --problem <text>
  omg crazy --problem <text>
  omg compat <list|contract|gap-report|snapshot|gate|run> [...]
  omg omc <compat-subcommand> [...]
  omg ecosystem <list|status|sync> [...]
  omg providers <status|smoke|repair> [...]
  omg release readiness
`;
  process.stderr.write(text);
  process.exit(2);
}

function parseFlags(args: string[]): Record<string, string | boolean> {
  const flags: Record<string, string | boolean> = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) {
      continue;
    }
    const key = arg.slice(2);
    const next = args[index + 1];
    if (!next || next.startsWith("--")) {
      flags[key] = true;
      continue;
    }
    flags[key] = next;
    index += 1;
  }
  return flags;
}

function splitFiles(value: string | boolean | undefined): string[] {
  if (typeof value !== "string") {
    return [];
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function main(argv = process.argv.slice(2)): Promise<number> {
  let [command, maybeSubcommand, ...rest] = argv;
  let subcommand = maybeSubcommand || "";
  if (subcommand.startsWith("--")) {
    rest = [subcommand, ...rest];
    subcommand = "";
  }
  const flags = parseFlags(rest);
  const projectDir = ensureProjectDir();

  if (!command) {
    usage();
  }

  if (command === "ship") {
    const ideaPath = String(flags.idea || ".omg/idea.yml");
    const runtime = String(flags.runtime || "claude");
    const idea = loadIdea(ideaPath);
    const dispatched = dispatchRuntime(runtime, idea);
    const runId = String(flags["run-id"] || nowRunId());
    const evidencePath = createEvidencePack(projectDir, runId, {
      tests: (dispatched.verification as any)?.checks || [],
      diff_summary: { runtime, goal: String(idea.goal || "") },
      reproducibility: { command: `omg ship --runtime ${runtime} --idea ${ideaPath}` }
    });
    printJson({
      status: "ok",
      command: "ship",
      runtime,
      run_id: runId,
      goal: String(idea.goal || ""),
      evidence_path: relativeToProject(projectDir, evidencePath)
    });
    return 0;
  }

  if (command === "fix") {
    const runtime = String(flags.runtime || "claude");
    const issue = String(flags.issue || "");
    const result = dispatchRuntime(runtime, {
      goal: `Fix issue ${issue}`,
      acceptance: [`issue-${issue}-resolved`]
    });
    printJson(result);
    return result.status === "ok" ? 0 : 2;
  }

  if (command === "secure") {
    const result = evaluateBashCommand(String(flags.command || ""));
    printJson(result);
    return result.action === "deny" ? 3 : 0;
  }

  if (command === "maintainer") {
    const path = join(projectDir, ".omg", "evidence", "oss-impact.json");
    const payload = {
      status: "ok",
      path,
      generated_at: new Date().toISOString(),
      mode: String(flags.mode || "impact"),
      activity: { commits: "unverified", reviews: "unverified", releases: "unverified" }
    };
    ensureParent(path);
    Bun.write(path, JSON.stringify(payload, null, 2));
    printJson(payload);
    return 0;
  }

  if (command === "trust" && subcommand === "review") {
    const oldCfg = loadJson(String(flags.old || ""));
    const newCfg = loadJson(String(flags.new || ""));
    const review = reviewConfigChange(String(flags.file || "settings.json"), oldCfg, newCfg);
    const manifest = writeTrustManifest(projectDir, review);
    printJson({ review, manifest });
    return 0;
  }

  if (command === "runtime" && subcommand === "dispatch") {
    const runtime = String(flags.runtime || "claude");
    const idea = flags["idea-json"] ? loadIdea(String(flags["idea-json"]), true) : loadIdea(String(flags.idea || "{}"));
    const result = dispatchRuntime(runtime, idea);
    printJson(result);
    return result.status === "ok" ? 0 : 2;
  }

  if (command === "teams") {
    const result = dispatchTeam({
      target: String(flags.target || "auto"),
      problem: String(flags.problem || ""),
      context: String(flags.context || ""),
      files: splitFiles(flags.files),
      expected_outcome: String(flags["expected-outcome"] || "")
    });
    printJson(result);
    return 0;
  }

  if (command === "ccg") {
    const result = executeCcgMode({
      problem: String(flags.problem || ""),
      project_dir: projectDir,
      context: String(flags.context || ""),
      files: splitFiles(flags.files)
    });
    printJson(result);
    return 0;
  }

  if (command === "crazy") {
    const result = executeCrazyMode({
      problem: String(flags.problem || ""),
      project_dir: projectDir,
      context: String(flags.context || ""),
      files: splitFiles(flags.files)
    });
    printJson(result);
    return 0;
  }

  if ((command === "compat" || command === "omc") && subcommand === "list") {
    const skills = listCompatSkills();
    printJson({ status: "ok", count: skills.length, skills });
    return 0;
  }

  if ((command === "compat" || command === "omc") && subcommand === "contract") {
    if (flags.all) {
      const contracts = listCompatSkillContracts();
      printJson({ status: "ok", count: contracts.length, contracts });
      return 0;
    }
    const skill = String(flags.skill || "");
    const contract = getCompatSkillContract(skill);
    if (!contract) {
      printJson({ status: "error", message: `Unknown skill: ${skill}` });
      return 2;
    }
    printJson({ status: "ok", contract });
    return 0;
  }

  if ((command === "compat" || command === "omc") && subcommand === "gap-report") {
    const report = buildCompatGapReport(projectDir);
    const output = String(flags.output || DEFAULT_GAP_REPORT_PATH);
    ensureParent(output);
    Bun.write(output, JSON.stringify(report, null, 2));
    printJson({ status: "ok", report });
    return 0;
  }

  if ((command === "compat" || command === "omc") && subcommand === "snapshot") {
    const payload = buildContractSnapshotPayload({ includeGeneratedAt: true });
    const output = String(flags.output || DEFAULT_CONTRACT_SNAPSHOT_PATH);
    ensureParent(output);
    Bun.write(output, JSON.stringify(payload, null, 2));
    printJson({ status: "ok", output, count: payload.count });
    return 0;
  }

  if ((command === "compat" || command === "omc") && subcommand === "gate") {
    const report = buildCompatGapReport(projectDir);
    const output = String(flags.output || DEFAULT_GAP_REPORT_PATH);
    ensureParent(output);
    Bun.write(output, JSON.stringify(report, null, 2));
    const maxBridge = Number(flags["max-bridge"] || 0);
    const bridgeCount = Number((report.maturity_counts as Record<string, number>).bridge || 0);
    if (bridgeCount > maxBridge) {
      printJson({
        status: "error",
        message: `OMG compat gate failed: bridge=${bridgeCount} > max_bridge=${maxBridge}`,
        report
      });
      return 3;
    }
    printJson({
      status: "ok",
      message: `OMG compat gate passed: bridge=${bridgeCount} <= max_bridge=${maxBridge}`,
      report
    });
    return 0;
  }

  if ((command === "compat" || command === "omc") && subcommand === "run") {
    const result = dispatchCompatSkill({
      skill: String(flags.skill || ""),
      problem: String(flags.problem || ""),
      context: String(flags.context || ""),
      files: splitFiles(flags.files),
      expected_outcome: String(flags["expected-outcome"] || ""),
      project_dir: projectDir
    });
    printJson(result);
    return result.status === "ok" ? 0 : 2;
  }

  if (command === "ecosystem" && subcommand === "list") {
    const repos = listEcosystemRepos();
    printJson({ status: "ok", count: repos.length, repos });
    return 0;
  }

  if (command === "ecosystem" && subcommand === "status") {
    printJson(ecosystemStatus({ project_dir: projectDir }));
    return 0;
  }

  if (command === "ecosystem" && subcommand === "sync") {
    const result = syncEcosystemRepos({
      project_dir: projectDir,
      names: splitFiles(flags.names),
      update: Boolean(flags.update),
      depth: Number(flags.depth || 1)
    });
    printJson(result);
    return 0;
  }

  if (command === "providers" && subcommand === "status") {
    const result = collectProviderStatusWithOptions(projectDir, {
      includeSmoke: Boolean(flags.smoke),
      smokeHostMode: String(flags["host-mode"] || "claude_dispatch")
    });
    printJson(result);
    return 0;
  }

  if (command === "providers" && subcommand === "smoke") {
    const result = runProviderSmokeMatrix({
      project_dir: projectDir,
      provider: String(flags.provider || "all"),
      host_mode: String(flags["host-mode"] || "claude_dispatch")
    });
    printJson(result);
    return 0;
  }

  if (command === "providers" && subcommand === "repair") {
    const result = repairProviderHosts(projectDir, String(flags.provider || ""));
    printJson(result);
    return 0;
  }

  if (command === "release" && subcommand === "readiness") {
    printJson(collectReleaseReadiness(projectDir));
    return 0;
  }

  usage();
}

if (import.meta.main) {
  const exitCode = await main();
  process.exit(exitCode);
}
