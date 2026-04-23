import { resolve } from "node:path";
import type { CommandModule } from "yargs";
import {
  SUPPORTED_DEPLOY_TARGETS,
  detectDeployTarget,
  deploy,
  type DeployTarget,
} from "../../deploy/integrations.js";

interface DeployArgs {
  readonly target?: DeployTarget;
  readonly dryRun?: boolean;
  readonly json?: boolean;
  readonly projectDir?: string;
}

export const deployCommand: CommandModule<object, DeployArgs> = {
  command: "deploy",
  describe: "Deploy the current project to the detected provider",
  builder: {
    target: {
      type: "string",
      choices: [...SUPPORTED_DEPLOY_TARGETS],
      description: "Override detected deploy target",
    },
    "dry-run": {
      type: "boolean",
      description: "Show detected target and deploy command without executing",
      default: false,
    },
    json: {
      type: "boolean",
      description: "Output deploy result as JSON",
      default: false,
    },
    "project-dir": {
      type: "string",
      description: "Project directory override",
    },
  },
  handler: async (argv): Promise<void> => {
    const projectDir = resolve(argv.projectDir ?? process.cwd());
    const target = (argv.target ??
      detectDeployTarget(projectDir)) as DeployTarget;
    const result = await deploy(target, projectDir, Boolean(argv.dryRun));
    const payload = {
      target,
      projectDir,
      dryRun: Boolean(argv.dryRun),
      ...result,
    } as const;

    if (argv.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(`Deploy target: ${payload.target}`);
      console.log(`Deploy status: ${payload.success ? "ready" : "failed"}`);
      console.log(`Project dir: ${payload.projectDir}`);
      console.log(`Message: ${payload.message}`);
      if (payload.url) {
        console.log(`URL: ${payload.url}`);
      }
    }

    if (!payload.success) {
      process.exitCode = 1;
    }
  },
};
