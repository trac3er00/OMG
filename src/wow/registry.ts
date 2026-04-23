import type { WowFlow } from "./schema.js";

export const flows: Record<string, WowFlow> = {
  landing: {
    name: "landing",
    description: "Landing page",
    expectedArtifact: "index.html",
    proofFloor: 70,
    timeout: 120000,
    toolAllowlist: ["bash", "write"],
    deployable: true,
  },
  saas: {
    name: "saas",
    description: "SaaS starter",
    expectedArtifact: "package.json",
    proofFloor: 70,
    timeout: 180000,
    toolAllowlist: ["bash", "write"],
    deployable: true,
  },
  bot: {
    name: "bot",
    description: "Discord/Telegram bot",
    expectedArtifact: "package.json",
    proofFloor: 60,
    timeout: 120000,
    toolAllowlist: ["bash", "write"],
    deployable: false,
  },
  admin: {
    name: "admin",
    description: "Admin dashboard",
    expectedArtifact: "index.html",
    proofFloor: 70,
    timeout: 150000,
    toolAllowlist: ["bash", "write"],
    deployable: true,
  },
  refactor: {
    name: "refactor",
    description: "Repo refactor",
    expectedArtifact: "diff",
    proofFloor: 60,
    timeout: 180000,
    toolAllowlist: ["bash", "read"],
    deployable: false,
  },
};

export function getFlow(name: string): WowFlow | undefined {
  return flows[name];
}
