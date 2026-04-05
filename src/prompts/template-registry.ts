import { z } from "zod";

export const PROMPTS_VERSION = "1.0.0";

export type TaskType =
  | "code-review"
  | "security-audit"
  | "planning"
  | "debugging"
  | "documentation";

export const PromptTemplateSchema = z.object({
  template_id: z.string(),
  task_type: z.enum([
    "code-review",
    "security-audit",
    "planning",
    "debugging",
    "documentation",
  ]),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  content: z.string().min(1),
  few_shot_examples: z.array(
    z.object({
      input: z.string(),
      output: z.string(),
      quality_score: z.number().min(0).max(1),
    }),
  ),
  chain_of_thought: z.boolean().default(false),
  output_schema: z.string().optional(),
  created_at: z.string(),
});
export type PromptTemplate = z.infer<typeof PromptTemplateSchema>;

export interface TemplateMatch {
  readonly template: PromptTemplate;
  readonly version: string;
}

const templateRegistry = new Map<string, Map<string, PromptTemplate>>();

export function registerTemplate(template: PromptTemplate): void {
  const validated = PromptTemplateSchema.parse(template);
  if (!templateRegistry.has(validated.task_type)) {
    templateRegistry.set(validated.task_type, new Map());
  }
  templateRegistry.get(validated.task_type)!.set(validated.version, validated);
}

export function getTemplate(
  taskType: TaskType,
  version?: string,
): TemplateMatch | null {
  const versions = templateRegistry.get(taskType);
  if (versions == null || versions.size === 0) return null;

  if (version != null) {
    const t = versions.get(version);
    return t ? { template: t, version } : null;
  }

  const latest = [...versions.entries()].sort(([a], [b]) =>
    b.localeCompare(a),
  )[0];
  if (!latest) return null;
  return { template: latest[1], version: latest[0] };
}

export function listTaskTypes(): string[] {
  return [...templateRegistry.keys()];
}

export function buildPrompt(
  template: PromptTemplate,
  context: Record<string, string>,
): string {
  let prompt = template.content;
  for (const [key, value] of Object.entries(context)) {
    prompt = prompt.replace(`{{${key}}}`, value);
  }
  if (template.chain_of_thought) {
    prompt += "\n\nThink step by step before giving your final answer.";
  }
  return prompt;
}

export function clearTemplateRegistry(): void {
  templateRegistry.clear();
}
