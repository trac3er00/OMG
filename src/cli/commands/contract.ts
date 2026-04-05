import type { CommandModule } from "yargs";
import { CANONICAL_VERSION } from "../../runtime/canonical-taxonomy.js";
import {
  compileContract,
  validateContract,
  type ContractHost,
  type ContractSchema,
} from "../../runtime/contract-compiler/index.js";

const CANONICAL_HOSTS: readonly ContractHost[] = [
  "claude",
  "codex",
  "gemini",
  "kimi",
];

function defaultSchema(): ContractSchema {
  return {
    version: CANONICAL_VERSION,
    capabilities: [
      "compilation_targets",
      "hooks",
      "subagents",
      "skills",
      "agents_fragments",
      "rules",
      "automations",
      "mcp",
    ],
    hosts: [...CANONICAL_HOSTS],
    tools: {
      "control-plane": {
        description: "Canonical OMG control-plane MCP server",
        hosts: ["claude", "codex", "gemini", "kimi"],
      },
      "session-health": {
        description: "Session health monitoring and reporting",
        hosts: ["claude", "codex", "gemini", "kimi"],
      },
      "claim-judge": {
        description: "Evidence-backed claim verification",
        hosts: ["claude", "codex", "gemini", "kimi"],
      },
      "test-intent-lock": {
        description: "Test weakening detection and prevention",
        hosts: ["claude", "codex", "gemini", "kimi"],
      },
    },
  };
}

function isContractHost(value: string): value is ContractHost {
  return CANONICAL_HOSTS.includes(value as ContractHost);
}

interface ContractValidateArgs {
  json?: boolean;
}

export const contractValidateCommand: CommandModule<
  object,
  ContractValidateArgs
> = {
  command: "validate",
  describe: "Validate the canonical contract schema",
  builder: (yargs) =>
    yargs.option("json", {
      type: "boolean",
      description: "Output as JSON",
      default: false,
    }),
  handler: (argv): void => {
    const schema = defaultSchema();
    const result = validateContract(schema);
    const payload = {
      status: result.valid ? "pass" : "fail",
      blockers: result.blockers,
      version: schema.version,
      hosts: schema.hosts,
    };

    if (argv.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(`contract validate: ${payload.status}`);
      if (result.blockers.length > 0) {
        for (const blocker of result.blockers) {
          console.log(`  blocker: ${blocker}`);
        }
      }
      console.log(`  version: ${schema.version}`);
      console.log(`  hosts: ${schema.hosts.join(", ")}`);
    }

    if (!result.valid) {
      process.exitCode = 1;
    }
  },
};

interface ContractCompileArgs {
  host?: string[];
  channel?: string;
  json?: boolean;
}

export const contractCompileCommand: CommandModule = {
  command: "compile",
  describe: "Compile contract artifacts for target hosts",
  builder: (yargs) =>
    yargs
      .option("host", {
        type: "string",
        array: true,
        describe: "Target host(s): claude, codex, gemini, kimi",
      })
      .option("channel", {
        type: "string",
        describe: "Release channel (public, internal)",
        default: "public",
      })
      .option("json", {
        type: "boolean",
        description: "Output as JSON",
        default: false,
      }),
  handler: (argv): void => {
    const args = argv as unknown as ContractCompileArgs;
    const schema = defaultSchema();

    const rawHosts: string[] = args.host ?? [...CANONICAL_HOSTS];
    const invalidHosts = rawHosts.filter((h) => !isContractHost(h));
    if (invalidHosts.length > 0) {
      console.error(`error: unsupported host(s): ${invalidHosts.join(", ")}`);
      console.error(`  supported: ${CANONICAL_HOSTS.join(", ")}`);
      process.exitCode = 1;
      return;
    }

    const targetHosts = rawHosts as ContractHost[];
    const result = compileContract(schema, targetHosts);

    const payload = {
      status: result.valid ? "SUCCESS" : "FAIL",
      hosts: targetHosts,
      channel: args.channel ?? "public",
      blockers: result.blockers,
      artifacts: result.artifacts.map((a) => ({
        host: a.host,
        targetPath: a.targetPath,
      })),
      version: schema.version,
    };

    if (args.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      for (const host of targetHosts) {
        const artifact = result.artifacts.find((a) => a.host === host);
        if (artifact) {
          console.log(`[${host}] compiled -> ${artifact.targetPath}`);
        } else if (!result.valid) {
          console.log(`[${host}] blocked`);
          for (const blocker of result.blockers) {
            console.log(`  blocker: ${blocker}`);
          }
        }
      }
      console.log(`\ncontract compile: ${payload.status}`);
      console.log(`  version: ${schema.version}`);
      console.log(`  channel: ${payload.channel}`);
      console.log(`  hosts: ${targetHosts.join(", ")}`);
    }

    if (!result.valid) {
      process.exitCode = 1;
    }
  },
};

export const contractCommand: CommandModule = {
  command: "contract",
  describe: "Contract compilation and validation",
  builder: (yargs) =>
    yargs
      .command(contractValidateCommand)
      .command(contractCompileCommand)
      .demandCommand(1, "Specify a contract subcommand: validate or compile"),
  handler: () => {},
};
