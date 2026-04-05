import { z } from "zod";

export type DomainType = "web_app" | "cli_tool" | "backend_api" | "unknown";
export const SUPPORTED_DOMAINS: DomainType[] = [
  "web_app",
  "cli_tool",
  "backend_api",
];

export const DomainDetectionResultSchema = z.object({
  primary_domain: z.enum(["web_app", "cli_tool", "backend_api", "unknown"]),
  all_domains: z.array(
    z.enum(["web_app", "cli_tool", "backend_api", "unknown"]),
  ),
  confidence_scores: z.record(z.string(), z.number().min(0).max(1)),
  framework_hints: z.array(z.string()),
  detected_at: z.string(),
});
export type DomainDetectionResult = z.infer<typeof DomainDetectionResultSchema>;

export interface DetectionSignals {
  readonly dependencies: Record<string, string>;
  readonly files: readonly string[];
  readonly scripts: Record<string, string>;
}

const WEB_APP_DEPS = new Set([
  "react",
  "vue",
  "next",
  "nuxt",
  "svelte",
  "angular",
  "vite",
  "remix",
]);
const CLI_DEPS = new Set([
  "commander",
  "yargs",
  "meow",
  "clipanion",
  "oclif",
  "arg",
]);
const API_DEPS = new Set([
  "express",
  "fastify",
  "koa",
  "hono",
  "fastapi",
  "flask",
  "django",
]);

const WEB_FILES = [
  /\.tsx$/,
  /\.jsx$/,
  /public\/index\.html/,
  /tailwind\.config/,
  /vite\.config/,
  /next\.config/,
];
const CLI_FILES = [/^bin\//, /cli\.ts$/, /cli\.js$/, /^commands\//];
const API_FILES = [
  /Dockerfile/,
  /openapi\.(yaml|json)/,
  /swagger\./,
  /routes\//,
  /controllers\//,
];

function scoreDomain(
  domain: Exclude<DomainType, "unknown">,
  signals: DetectionSignals,
): number {
  let score = 0;
  const weights = { dep: 0.4, file: 0.4, script: 0.2 };
  const deps = Object.keys(signals.dependencies);
  const depSet =
    domain === "web_app"
      ? WEB_APP_DEPS
      : domain === "cli_tool"
        ? CLI_DEPS
        : API_DEPS;
  const filePatterns =
    domain === "web_app"
      ? WEB_FILES
      : domain === "cli_tool"
        ? CLI_FILES
        : API_FILES;

  const depHits = deps.filter((d) => depSet.has(d.toLowerCase())).length;
  if (depHits > 0) score += weights.dep * Math.min(1, depHits / 2);

  const fileHits = signals.files.filter((f) =>
    filePatterns.some((p) => p.test(f)),
  ).length;
  if (fileHits > 0) score += weights.file * Math.min(1, fileHits / 3);

  const scriptValues = Object.values(signals.scripts).join(" ").toLowerCase();
  if (domain === "web_app" && /dev|build|preview/.test(scriptValues))
    score += weights.script * 0.5;
  if (domain === "cli_tool" && /bin|cli/.test(scriptValues))
    score += weights.script * 0.5;
  if (domain === "backend_api" && /serve|start|server/.test(scriptValues))
    score += weights.script * 0.5;

  return Math.min(1, score);
}

export function detectDomain(signals: DetectionSignals): DomainDetectionResult {
  const scores: Record<string, number> = {
    web_app: scoreDomain("web_app", signals),
    cli_tool: scoreDomain("cli_tool", signals),
    backend_api: scoreDomain("backend_api", signals),
  };

  const detected: DomainType[] = (
    Object.entries(scores) as [DomainType, number][]
  )
    .filter(([, s]) => s >= 0.2)
    .sort(([, a], [, b]) => b - a)
    .map(([d]) => d);

  const primary_domain: DomainType = detected[0] ?? "unknown";
  const framework_hints: string[] = [];

  const deps = Object.keys(signals.dependencies).map((d) => d.toLowerCase());
  for (const dep of deps) {
    if (WEB_APP_DEPS.has(dep) || CLI_DEPS.has(dep) || API_DEPS.has(dep)) {
      framework_hints.push(dep);
    }
  }

  return DomainDetectionResultSchema.parse({
    primary_domain,
    all_domains: detected.length > 0 ? detected : ["unknown"],
    confidence_scores: scores,
    framework_hints: framework_hints.slice(0, 5),
    detected_at: new Date().toISOString(),
  });
}
