import { execSync } from "node:child_process";
import type { CommandModule } from "yargs";

const VALID_CATEGORIES = [
  "decisions",
  "preferences",
  "failures",
  "open_loops",
  "team_context",
] as const;

type MemoryCategory = (typeof VALID_CATEGORIES)[number];

interface MemoryShowArgs {
  readonly category?: string;
}

function buildSchemaCommand(
  projectDir: string,
  category: MemoryCategory,
): string {
  const escaped = projectDir.replace(/'/g, "\\'");
  return [
    "python3",
    "-c",
    `'import sys; sys.path.insert(0, "${escaped}"); ` +
      `from runtime.memory_schema import get_schema_description; ` +
      `print(get_schema_description("${category}"))'`,
  ].join(" ");
}

export async function runMemoryShow(category?: string): Promise<void> {
  const projectDir = process.cwd();

  if (!category) {
    console.log("Available memory categories:");
    VALID_CATEGORIES.forEach((entry) => {
      console.log(`  ${entry}`);
    });
    console.log("\nUsage: npx omg memory show <category>");
    return;
  }

  if (!VALID_CATEGORIES.includes(category as MemoryCategory)) {
    console.error(
      `Unknown category: ${category}. Valid: ${VALID_CATEGORIES.join(", ")}`,
    );
    process.exit(1);
  }

  const safeCategory = category as MemoryCategory;

  console.log(`Memory category: ${safeCategory}`);
  console.log("(Schema validation available via runtime.memory_schema)");
  console.log("\nCategory schema:");

  try {
    const desc = execSync(buildSchemaCommand(projectDir, safeCategory), {
      encoding: "utf8",
      cwd: projectDir,
      timeout: 30_000,
    }).trimEnd();
    console.log(desc);
  } catch {
    console.log(`Category: ${safeCategory} (schema info unavailable)`);
  }
}

export const memoryCommand: CommandModule<object, MemoryShowArgs> = {
  command: "memory",
  describe: "Inspect structured memory categories",
  builder: (yargs) =>
    yargs
      .command(
        "show [category]",
        "Show a structured memory category schema",
        (command) =>
          command.positional("category", {
            type: "string",
            describe: "Structured memory category",
          }),
        async (argv) => {
          await runMemoryShow(argv.category);
        },
      )
      .demandCommand(1, "Specify a memory subcommand: show"),
  handler: () => {},
};
