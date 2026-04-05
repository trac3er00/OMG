import { spawn, type ChildProcess } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { AgentConfig as AgentConfigInput } from "../interfaces/orchestration.js";

export enum AgentState {
  PENDING = "PENDING",
  RUNNING = "RUNNING",
  COMPLETED = "COMPLETED",
  FAILED = "FAILED",
  CANCELLED = "CANCELLED",
}

export interface AgentRunResult {
  readonly returnCode: number;
  readonly stdout: string;
  readonly stderr: string;
  readonly elapsedSeconds: number;
}

export interface AgentRecord {
  readonly id: string;
  readonly config: AgentConfigInput;
  readonly projectDir: string;
  state: AgentState;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  result?: AgentRunResult;
  error?: string;
  pid?: number;
  process?: ChildProcess;
}

export interface AgentManagerOptions {
  readonly projectDir?: string;
  readonly spawnProcess?: (
    config: AgentConfigInput,
    cwd: string,
  ) => ChildProcess;
  readonly idGenerator?: () => string;
  readonly now?: () => Date;
  readonly cancelKillDelayMs?: number;
}

class AsyncMutex {
  private locked = false;

  private readonly waiters: Array<() => void> = [];

  async acquire(): Promise<() => void> {
    if (!this.locked) {
      this.locked = true;
      return this.release;
    }

    await new Promise<void>((resolve) => {
      this.waiters.push(resolve);
    });
    this.locked = true;
    return this.release;
  }

  private readonly release = (): void => {
    const waiter = this.waiters.shift();
    if (waiter === undefined) {
      this.locked = false;
      return;
    }
    waiter();
  };
}

const MODULE_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(MODULE_DIR, "../..");

function defaultIdGenerator(): string {
  return `subagent-${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
}

function defaultSpawnProcess(config: AgentConfigInput, cwd: string): ChildProcess {
  const bun = process.env.OMG_BUN ?? "bun";
  const omgScript = resolve(REPO_ROOT, "src/cli/index.ts");
  const args = ["run", omgScript, "task", "--category", config.category, "--prompt", config.prompt];

  if (config.skills.length > 0) {
    args.push("--skills", config.skills.join(","));
  }

  if (config.subagentType !== undefined && config.subagentType.trim().length > 0) {
    args.push("--subagent-type", config.subagentType);
  }

  return spawn(bun, args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function formatError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export class AgentManager {
  static create(options: AgentManagerOptions = {}): AgentManager {
    return new AgentManager(options);
  }

  private readonly mutex = new AsyncMutex();

  private readonly agents = new Map<string, AgentRecord>();

  private readonly projectDir: string;

  private readonly spawnProcess: (
    config: AgentConfigInput,
    cwd: string,
  ) => ChildProcess;

  private readonly idGenerator: () => string;

  private readonly now: () => Date;

  private readonly cancelKillDelayMs: number;

  constructor(options: AgentManagerOptions = {}) {
    this.projectDir = options.projectDir ?? process.cwd();
    this.spawnProcess = options.spawnProcess ?? defaultSpawnProcess;
    this.idGenerator = options.idGenerator ?? defaultIdGenerator;
    this.now = options.now ?? (() => new Date());
    this.cancelKillDelayMs = options.cancelKillDelayMs ?? 2_000;
  }

  async spawnAgent(config: AgentConfigInput): Promise<string> {
    const id = this.idGenerator();
    const createdAt = this.now().toISOString();
    const release = await this.mutex.acquire();

    try {
      this.agents.set(id, {
        id,
        config,
        projectDir: this.projectDir,
        state: AgentState.PENDING,
        createdAt,
      });
    } finally {
      release();
    }

    void this.startAgent(id);
    return id;
  }

  async cancelAgent(id: string): Promise<boolean> {
    const release = await this.mutex.acquire();
    let processRef: ChildProcess | undefined;

    try {
      const agent = this.agents.get(id);
      if (agent === undefined) {
        return false;
      }

      if (
        agent.state === AgentState.COMPLETED
        || agent.state === AgentState.FAILED
        || agent.state === AgentState.CANCELLED
      ) {
        return false;
      }

      agent.state = AgentState.CANCELLED;
      agent.completedAt = this.now().toISOString();
      processRef = agent.process;
    } finally {
      release();
    }

    if (processRef !== undefined) {
      processRef.kill("SIGTERM");
      setTimeout(() => {
        if (!processRef.killed) {
          processRef.kill("SIGKILL");
        }
      }, this.cancelKillDelayMs);
    }

    return true;
  }

  async getState(id: string): Promise<AgentState | undefined> {
    const release = await this.mutex.acquire();
    try {
      return this.agents.get(id)?.state;
    } finally {
      release();
    }
  }

  private async startAgent(id: string): Promise<void> {
    const release = await this.mutex.acquire();
    let config: AgentConfigInput | undefined;

    try {
      const agent = this.agents.get(id);
      if (agent === undefined || agent.state === AgentState.CANCELLED) {
        return;
      }

      agent.state = AgentState.RUNNING;
      agent.startedAt = this.now().toISOString();
      config = agent.config;
    } finally {
      release();
    }

    if (config === undefined) {
      return;
    }

    const startedAtMs = this.now().getTime();
    let child: ChildProcess;

    try {
      child = this.spawnProcess(config, this.projectDir);
    } catch (error) {
      await this.markFailure(id, formatError(error));
      return;
    }

    const bindRelease = await this.mutex.acquire();
    try {
      const agent = this.agents.get(id);
      if (agent === undefined || agent.state === AgentState.CANCELLED) {
        child.kill("SIGTERM");
        return;
      }
      agent.process = child;
      if (typeof child.pid === "number") {
        agent.pid = child.pid;
      } else {
        delete agent.pid;
      }
    } finally {
      bindRelease();
    }

    let stdout = "";
    let stderr = "";

    child.stdout?.setEncoding("utf8");
    child.stdout?.on("data", (chunk: string | Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr?.setEncoding("utf8");
    child.stderr?.on("data", (chunk: string | Buffer) => {
      stderr += chunk.toString();
    });

    const timeoutMs = Math.max(1, config.timeout) * 1_000;
    const timeout = setTimeout(() => {
      const timeoutText = `Timeout after ${config.timeout}s`;
      child.kill("SIGTERM");
      void this.markFailure(id, timeoutText);
    }, timeoutMs);

    child.once("error", (error) => {
      clearTimeout(timeout);
      void this.markFailure(id, formatError(error));
    });

    child.once("exit", (code) => {
      clearTimeout(timeout);
      const elapsedSeconds = (this.now().getTime() - startedAtMs) / 1_000;
      void this.finalizeExit(id, {
        returnCode: code ?? -1,
        stdout,
        stderr,
        elapsedSeconds,
      });
    });
  }

  private async markFailure(id: string, errorText: string): Promise<void> {
    const release = await this.mutex.acquire();
    try {
      const agent = this.agents.get(id);
      if (agent === undefined || agent.state === AgentState.CANCELLED) {
        return;
      }
      agent.state = AgentState.FAILED;
      agent.error = errorText;
      agent.completedAt = this.now().toISOString();
    } finally {
      release();
    }
  }

  private async finalizeExit(id: string, result: AgentRunResult): Promise<void> {
    const release = await this.mutex.acquire();
    try {
      const agent = this.agents.get(id);
      if (agent === undefined) {
        return;
      }
      agent.result = result;
      delete agent.process;
      agent.completedAt = this.now().toISOString();

      if (agent.state === AgentState.CANCELLED) {
        return;
      }

      agent.state = result.returnCode === 0 ? AgentState.COMPLETED : AgentState.FAILED;
      if (result.returnCode !== 0) {
        agent.error = `Process exited with code ${result.returnCode}`;
      }
    } finally {
      release();
    }
  }
}
