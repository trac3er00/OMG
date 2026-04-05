import { z } from "zod";
import { type DomainType } from "./detection.js";

export const DomainAgentProfileSchema = z.object({
  domain: z.enum(["web_app", "cli_tool", "backend_api"]),
  agent_category: z.string(),
  harness_layer3_tool: z.enum(["playwright", "tmux", "curl"]),
  framework_hints: z.array(z.string()),
  verification_commands: z.array(z.string()),
});
export type DomainAgentProfile = z.infer<typeof DomainAgentProfileSchema>;

export const DOMAIN_PROFILES: Record<
  Exclude<DomainType, "unknown">,
  DomainAgentProfile
> = {
  web_app: DomainAgentProfileSchema.parse({
    domain: "web_app",
    agent_category: "visual-engineering",
    harness_layer3_tool: "playwright",
    framework_hints: ["react", "vue", "next", "svelte"],
    verification_commands: ["bun run build", "bun test --filter e2e"],
  }),
  cli_tool: DomainAgentProfileSchema.parse({
    domain: "cli_tool",
    agent_category: "deep",
    harness_layer3_tool: "tmux",
    framework_hints: ["commander", "yargs", "meow"],
    verification_commands: ["bun test", "node dist/cli.js --help"],
  }),
  backend_api: DomainAgentProfileSchema.parse({
    domain: "backend_api",
    agent_category: "deep",
    harness_layer3_tool: "curl",
    framework_hints: ["express", "fastify", "hono"],
    verification_commands: ["bun test", "curl -f http://localhost:3000/health"],
  }),
};

export function getDomainProfile(
  domain: DomainType,
): DomainAgentProfile | null {
  if (domain === "unknown") return null;
  return DOMAIN_PROFILES[domain] ?? null;
}

export function getVerificationTool(domain: DomainType): string {
  const profile = getDomainProfile(domain);
  return profile?.harness_layer3_tool ?? "curl";
}
