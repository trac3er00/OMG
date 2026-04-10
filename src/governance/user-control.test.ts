import { describe, expect, test } from "bun:test";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  formatGovernanceStatus,
  getUserGovernanceControl,
} from "./user-control.js";
import { checkMutationAllowed } from "../security/mutation-gate.js";
import { ToolFabric } from "./tool-fabric.js";

function mkProjectDir(label: string): string {
  return join(
    tmpdir(),
    `${label}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
}

describe("user governance control", () => {
  test("falls back to default config when governance file is missing", () => {
    const projectDir = mkProjectDir("governance-default");
    mkdirSync(projectDir, { recursive: true });

    try {
      const control = getUserGovernanceControl(projectDir);
      const mutationGate = control.getGateControl("MutationGate");

      expect(mutationGate.enabled).toBe(true);
      expect(mutationGate.enforcement).toBe("enforced");
      expect(mutationGate.source).toBe("default");
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  test("provider-specific overrides are resolved per gate", () => {
    const projectDir = mkProjectDir("governance-provider");
    mkdirSync(join(projectDir, ".omg"), { recursive: true });
    writeFileSync(
      join(projectDir, ".omg", "governance.yaml"),
      [
        "version: 1",
        "defaultProvider: claude",
        "gates:",
        "  MutationGate:",
        "    enabled: true",
        "    enforcement: enforced",
        "    providers:",
        "      ollama:",
        "        enabled: false",
        "  ToolFabric:",
        "    enabled: true",
        "    enforcement: enforced",
      ].join("\n"),
      "utf8",
    );

    try {
      const control = getUserGovernanceControl(projectDir);
      expect(control.getGateControl("MutationGate", "claude").enabled).toBe(
        true,
      );
      expect(control.getGateControl("MutationGate", "ollama").enabled).toBe(
        false,
      );
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  test("config changes are logged to the audit trail", () => {
    const projectDir = mkProjectDir("governance-audit");
    mkdirSync(join(projectDir, ".omg"), { recursive: true });
    const configPath = join(projectDir, ".omg", "governance.yaml");

    try {
      writeFileSync(
        configPath,
        "version: 1\ndefaultProvider: claude\ngates:\n  MutationGate:\n    enabled: true\n",
        "utf8",
      );

      const control = getUserGovernanceControl(projectDir);
      control.loadConfig();

      writeFileSync(
        configPath,
        "version: 1\ndefaultProvider: claude\ngates:\n  MutationGate:\n    enabled: false\n",
        "utf8",
      );

      control.loadConfig();

      const auditPath = join(projectDir, ".omg", "state", "ledger", "audit.jsonl");
      const auditLines = readFileSync(auditPath, "utf8")
        .trim()
        .split("\n")
        .map((line) => JSON.parse(line) as { action: string });

      expect(
        auditLines.filter((line) => line.action === "governance.config.changed")
          .length,
      ).toBe(2);
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  test("disabled mutation gate allows dangerous mutation and logs bypass", async () => {
    const projectDir = mkProjectDir("governance-mutation-bypass");
    mkdirSync(join(projectDir, ".omg"), { recursive: true });
    writeFileSync(
      join(projectDir, ".omg", "governance.yaml"),
      [
        "version: 1",
        "defaultProvider: claude",
        "gates:",
        "  MutationGate:",
        "    enabled: false",
        "    enforcement: advisory",
      ].join("\n"),
      "utf8",
    );

    try {
      const result = await checkMutationAllowed(
        "Bash",
        null,
        projectDir,
        null,
        null,
        "rm -rf /",
        "task-35",
      );

      expect(result.allowed).toBe(true);
      expect(result.reason).toContain("disabled by user governance");

      const auditPath = join(projectDir, ".omg", "state", "ledger", "audit.jsonl");
      const auditRaw = readFileSync(auditPath, "utf8");
      expect(auditRaw).toContain("governance.gate.bypass");
      expect(auditRaw).toContain("MutationGate");
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  test("disabled tool fabric allows restricted lane tool and reports status", async () => {
    const projectDir = mkProjectDir("governance-tool-fabric-bypass");
    mkdirSync(join(projectDir, ".omg"), { recursive: true });
    writeFileSync(
      join(projectDir, ".omg", "governance.yaml"),
      [
        "version: 1",
        "defaultProvider: claude",
        "gates:",
        "  ToolFabric:",
        "    enabled: false",
        "    enforcement: advisory",
      ].join("\n"),
      "utf8",
    );

    const fabric = new ToolFabric(projectDir);

    try {
      fabric.registerLane("restricted", { allowedTools: ["Read"] });
      const result = await fabric.evaluateRequest("Write", {}, "restricted");
      expect(result.action).toBe("allow");
      expect(result.reason).toContain("disabled by user governance");

      const status = formatGovernanceStatus(
        getUserGovernanceControl(projectDir).getStatus(),
      );
      expect(status).toContain("ToolFabric");
      expect(status).toContain("false");
    } finally {
      fabric.close();
      rmSync(projectDir, { recursive: true, force: true });
    }
  });
});

describe("governance status CLI", () => {
  test("prints current gate states", () => {
    const projectDir = mkProjectDir("governance-cli");
    mkdirSync(join(projectDir, ".omg"), { recursive: true });
    writeFileSync(
      join(projectDir, ".omg", "governance.yaml"),
      [
        "version: 1",
        "defaultProvider: claude",
        "gates:",
        "  MutationGate:",
        "    enabled: false",
        "  ToolFabric:",
        "    enabled: true",
        "    enforcement: advisory",
      ].join("\n"),
      "utf8",
    );

    try {
      const result = Bun.spawnSync({
        cmd: [
          "bun",
          "run",
          "src/cli/index.ts",
          "governance",
          "status",
          "--projectDir",
          projectDir,
        ],
        cwd: process.cwd(),
        stdout: "pipe",
        stderr: "pipe",
      });

      const stdout = new TextDecoder().decode(result.stdout).trim();
      expect(result.exitCode).toBe(0);
      expect(stdout).toContain("Governance status");
      expect(stdout).toContain("MutationGate");
      expect(stdout).toContain("ToolFabric");
    } finally {
      if (existsSync(projectDir)) {
        rmSync(projectDir, { recursive: true, force: true });
      }
    }
  });
});
