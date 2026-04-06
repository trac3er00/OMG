import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { CommandModule } from "yargs";

type SkillInfo = {
  readonly name: string;
  readonly description: string;
  readonly category: string;
};

const SKILLS_ROOT = resolve(
  fileURLToPath(new URL("../../../.agents/skills/omg", import.meta.url)),
);

const CATEGORY_RULES: ReadonlyArray<{
  readonly category: string;
  readonly matchers: readonly RegExp[];
}> = [
  {
    category: "Security",
    matchers: [/^hash-edit$/, /^security-check$/, /^test-intent-lock$/],
  },
  {
    category: "Governance",
    matchers: [
      /^control-plane$/,
      /^hook-governor$/,
      /^mcp-fabric$/,
      /^plan-council$/,
      /^preflight$/,
      /^proof-gate$/,
      /^remote-supervisor$/,
      /^terminal-lane$/,
      /^tracebank$/,
      /^delta-classifier$/,
    ],
  },
  {
    category: "Data",
    matchers: [/^api-twin$/, /^data-lineage$/],
  },
  {
    category: "Evaluation",
    matchers: [/^eval-gate$/, /^incident-replay$/, /^lsp-pack$/],
  },
  {
    category: "Infrastructure",
    matchers: [
      /^ast-pack$/,
      /^health$/,
      /^secure-worktree-pipeline$/,
      /^algorithms$/,
    ],
  },
  {
    category: "Robotics",
    matchers: [/^robotics$/, /^vision$/],
  },
];

function parseFrontmatter(contents: string): {
  name: string;
  description: string;
} {
  const nameMatch = contents.match(/^name:\s*(.+)$/m);
  const descriptionMatch = contents.match(/^description:\s*"?(.*?)"?$/m);

  return {
    name: nameMatch?.[1]?.trim() ?? "unknown",
    description: descriptionMatch?.[1]?.trim() ?? "",
  };
}

function resolveCategory(skillName: string): string {
  for (const rule of CATEGORY_RULES) {
    if (rule.matchers.some((matcher) => matcher.test(skillName))) {
      return rule.category;
    }
  }

  return "Other";
}

async function loadSkills(): Promise<SkillInfo[]> {
  const entries = await readdir(SKILLS_ROOT, { withFileTypes: true });
  const skills: SkillInfo[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const skillPath = resolve(SKILLS_ROOT, entry.name, "SKILL.md");
    const contents = await readFile(skillPath, "utf8");
    const { name, description } = parseFrontmatter(contents);
    skills.push({
      name,
      description,
      category: resolveCategory(entry.name),
    });
  }

  return skills.sort((left, right) => left.name.localeCompare(right.name));
}

function printSkills(skills: readonly SkillInfo[]): void {
  console.log("OMG Skills");
  console.log("");

  const grouped = new Map<string, SkillInfo[]>();
  for (const skill of skills) {
    const list = grouped.get(skill.category) ?? [];
    list.push(skill);
    grouped.set(skill.category, list);
  }

  for (const category of [
    "Security",
    "Governance",
    "Data",
    "Evaluation",
    "Infrastructure",
    "Robotics",
    "Other",
  ]) {
    const items = grouped.get(category);
    if (!items?.length) {
      continue;
    }

    console.log(`${category}:`);
    for (const skill of items) {
      console.log(`  ${skill.name} - ${skill.description}`);
    }
    console.log("");
  }
}

export const skillsListCommand: CommandModule = {
  command: "list",
  describe: "List available OMG skills",
  handler: async (): Promise<void> => {
    const skills = await loadSkills();
    printSkills(skills);
  },
};
