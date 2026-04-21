export type ChaosType =
  | "network-partition"
  | "memory-pressure"
  | "disk-exhaustion"
  | "slow-network"
  | "broken-pipe"
  | "malformed-json";

export interface ChaosOptions {
  readonly duration_ms?: number;
  readonly target?: string;
}

export type ChaosStatus = "active" | "clean" | "error";

interface ChaosEffectHandle {
  cleanup(): Promise<void>;
}

interface ChaosRuntime {
  apply(type: ChaosType, target: string): Promise<ChaosEffectHandle>;
}

interface ActiveEffect {
  readonly id: string;
  readonly handle: ChaosEffectHandle;
  timer: unknown;
}

interface ChaosInjectorConfig {
  readonly runtime?: ChaosRuntime;
  readonly setTimer?: (callback: () => void, delayMs: number) => unknown;
  readonly clearTimer?: (timer: unknown) => void;
  readonly commandExecutor?: CommandExecutor;
  readonly fileExists?: FileExistsFn;
  readonly readFile?: ReadFileFn;
}

const MAX_DURATION_MS = 60_000;

const DEFAULT_MEMORY_MB = 256;
const DEFAULT_MEMORY_TIMEOUT_SECONDS = 30;
const DEFAULT_DISK_MB = 1024;
const DEFAULT_DISK_FILE = "/tmp/chaos-disk";
const DEFAULT_MEMORY_TMPFS_FILE = "/dev/shm/chaos-memory.bin";

export interface NetworkFaultOptions {
  readonly delay_ms: number;
  readonly loss_pct?: number;
}

export interface MemoryFaultOptions {
  readonly memory_mb?: number;
  readonly timeout_s?: number;
}

export interface DiskFaultOptions {
  readonly size_mb?: number;
  readonly file_path?: string;
}

export interface FaultInjectionStatus {
  readonly status: ChaosStatus;
  readonly detail: string;
  readonly strategy?: string;
}

interface FaultInjectionResult extends FaultInjectionStatus {
  readonly handle?: ChaosEffectHandle;
}

interface CommandExecutionResult {
  readonly success: boolean;
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
}

type CommandExecutor = (
  command: readonly string[],
) => Promise<CommandExecutionResult>;

type FileExistsFn = (filePath: string) => Promise<boolean>;
type ReadFileFn = (filePath: string) => Promise<string>;

interface BunSpawnSyncResult {
  readonly success?: boolean;
  readonly exitCode?: number;
  readonly stdout?: unknown;
  readonly stderr?: unknown;
}

interface BunFileLike {
  exists(): Promise<boolean>;
  text(): Promise<string>;
}

interface BunLike {
  spawnSync?(options: { cmd: string[] }): BunSpawnSyncResult;
  file?(filePath: string): BunFileLike;
}

function decodeOutput(output: unknown): string {
  if (typeof output === "string") {
    return output;
  }
  if (output instanceof Uint8Array) {
    return new TextDecoder().decode(output);
  }
  if (output instanceof ArrayBuffer) {
    return new TextDecoder().decode(new Uint8Array(output));
  }
  return "";
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

async function defaultCommandExecutor(
  command: readonly string[],
): Promise<CommandExecutionResult> {
  const maybeBun = (globalThis as { Bun?: BunLike }).Bun;
  if (!maybeBun?.spawnSync) {
    return {
      success: false,
      exitCode: 127,
      stdout: "",
      stderr: "Bun.spawnSync is not available",
    };
  }

  try {
    const result = maybeBun.spawnSync({ cmd: [...command] });
    const exitCode =
      typeof result.exitCode === "number"
        ? result.exitCode
        : result.success
          ? 0
          : 1;

    return {
      success: result.success ?? exitCode === 0,
      exitCode,
      stdout: decodeOutput(result.stdout),
      stderr: decodeOutput(result.stderr),
    };
  } catch (error) {
    return {
      success: false,
      exitCode: 1,
      stdout: "",
      stderr: toErrorMessage(error),
    };
  }
}

async function defaultFileExists(filePath: string): Promise<boolean> {
  const maybeBun = (globalThis as { Bun?: BunLike }).Bun;

  if (maybeBun?.file) {
    try {
      return await maybeBun.file(filePath).exists();
    } catch {
      return false;
    }
  }

  const result = await defaultCommandExecutor(["test", "-f", filePath]);
  return result.success;
}

async function defaultReadFile(filePath: string): Promise<string> {
  const maybeBun = (globalThis as { Bun?: BunLike }).Bun;

  if (maybeBun?.file) {
    return await maybeBun.file(filePath).text();
  }

  const result = await defaultCommandExecutor(["cat", filePath]);
  if (!result.success) {
    throw new Error(`Failed reading ${filePath}: ${result.stderr}`);
  }
  return result.stdout;
}

function getNodeEnv(): string | undefined {
  return (
    globalThis as {
      process?: {
        env?: Record<string, string | undefined>;
      };
    }
  ).process?.env?.NODE_ENV;
}

function normalizeDuration(durationMs: number | undefined): number {
  if (durationMs === undefined) {
    return MAX_DURATION_MS;
  }

  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    throw new Error(
      `Chaos duration must be a positive number (received ${durationMs})`,
    );
  }

  const normalized = Math.floor(durationMs);
  if (normalized > MAX_DURATION_MS) {
    throw new Error(`Chaos duration exceeds max ${MAX_DURATION_MS}ms`);
  }

  return normalized;
}

function normalizeTarget(
  target: string,
  optionsTarget: string | undefined,
): string {
  const resolved = (optionsTarget ?? target).trim();
  if (resolved.length === 0) {
    throw new Error("Chaos target is required");
  }
  return resolved;
}

export class ChaosInjector {
  private readonly runtime: ChaosRuntime;
  private readonly setTimer: (callback: () => void, delayMs: number) => unknown;
  private readonly clearTimer: (timer: unknown) => void;
  private readonly commandExecutor: CommandExecutor;
  private readonly fileExists: FileExistsFn;
  private readonly readFile: ReadFileFn;

  private readonly iptablesCleanupCommands = new Map<string, readonly string[]>();
  private readonly diskArtifacts = new Set<string>();
  private readonly memoryArtifacts = new Set<string>();

  private readonly activeEffects = new Map<string, ActiveEffect>();
  private state: ChaosStatus = "clean";
  private sequence = 0;
  private queue: Promise<void> = Promise.resolve();

  public constructor(config: ChaosInjectorConfig = {}) {
    this.commandExecutor = config.commandExecutor ?? defaultCommandExecutor;
    this.fileExists = config.fileExists ?? defaultFileExists;
    this.readFile = config.readFile ?? defaultReadFile;

    this.runtime =
      config.runtime ??
      ({
        apply: async (type, target) => await this.applyBuiltInChaos(type, target),
      } satisfies ChaosRuntime);

    this.setTimer =
      config.setTimer ?? ((callback, delayMs) => setTimeout(callback, delayMs));
    this.clearTimer =
      config.clearTimer ??
      ((timer) => clearTimeout(timer as ReturnType<typeof setTimeout>));
  }

  public async injectNetworkFault(
    opts: NetworkFaultOptions,
  ): Promise<FaultInjectionResult> {
    await this.ensureDocker();

    try {
      const delayMs = Math.max(0, Math.floor(opts.delay_ms));
      const lossPct =
        opts.loss_pct === undefined
          ? undefined
          : clamp(Math.floor(opts.loss_pct), 0, 100);

      const tcCommand = [
        "tc",
        "qdisc",
        "add",
        "dev",
        "eth0",
        "root",
        "netem",
        "delay",
        `${delayMs}ms`,
      ];

      if (lossPct !== undefined) {
        tcCommand.push("loss", `${lossPct}%`);
      }

      const tcResult = await this.commandExecutor(tcCommand);
      if (tcResult.success) {
        return {
          status: "active",
          strategy: "tc-netem",
          detail: `Injected network fault via tc netem (delay=${delayMs}ms${lossPct !== undefined ? `, loss=${lossPct}%` : ""})`,
          handle: {
            cleanup: async (): Promise<void> => {
              const cleanupResult = await this.commandExecutor([
                "tc",
                "qdisc",
                "del",
                "dev",
                "eth0",
                "root",
                "netem",
              ]);
              if (!cleanupResult.success) {
                throw new Error(
                  `Failed to clear tc netem rule: ${cleanupResult.stderr || cleanupResult.stdout}`,
                );
              }
            },
          },
        };
      }

      const probability = clamp((lossPct ?? 50) / 100, 0.01, 1.0);
      const iptablesAdd = [
        "iptables",
        "-A",
        "OUTPUT",
        "-m",
        "statistic",
        "--mode",
        "random",
        "--probability",
        probability.toFixed(2),
        "-j",
        "DROP",
      ];

      const iptablesResult = await this.commandExecutor(iptablesAdd);
      if (!iptablesResult.success) {
        return {
          status: "error",
          strategy: "tc+iptables",
          detail:
            `Network injection failed. ` +
            `tc: ${tcResult.stderr || tcResult.stdout || "unknown"}; ` +
            `iptables: ${iptablesResult.stderr || iptablesResult.stdout || "unknown"}`,
        };
      }

      const iptablesCleanup = ["iptables", "-D", ...iptablesAdd.slice(2)] as const;
      const cleanupKey = iptablesCleanup.join("\u0000");
      this.iptablesCleanupCommands.set(cleanupKey, iptablesCleanup);

      return {
        status: "active",
        strategy: "iptables-drop",
        detail: `Injected network fault via iptables DROP (probability=${probability.toFixed(2)})`,
        handle: {
          cleanup: async (): Promise<void> => {
            const cleanupResult = await this.commandExecutor(iptablesCleanup);
            this.iptablesCleanupCommands.delete(cleanupKey);
            if (!cleanupResult.success) {
              throw new Error(
                `Failed to clear iptables rule: ${cleanupResult.stderr || cleanupResult.stdout}`,
              );
            }
          },
        },
      };
    } catch (error) {
      return {
        status: "error",
        strategy: "network",
        detail: `Network fault injection failed: ${toErrorMessage(error)}`,
      };
    }
  }

  public async injectMemoryPressure(
    opts: MemoryFaultOptions = {},
  ): Promise<FaultInjectionResult> {
    await this.ensureDocker();

    try {
      const memoryMb = Math.max(1, Math.floor(opts.memory_mb ?? DEFAULT_MEMORY_MB));
      const timeoutSeconds = Math.max(
        1,
        Math.floor(opts.timeout_s ?? DEFAULT_MEMORY_TIMEOUT_SECONDS),
      );

      const stressCommand = [
        "stress-ng",
        "--vm",
        "1",
        "--vm-bytes",
        `${memoryMb}M`,
        "--timeout",
        `${timeoutSeconds}s`,
        "--background",
      ];

      const stressResult = await this.commandExecutor(stressCommand);
      if (stressResult.success) {
        return {
          status: "active",
          strategy: "stress-ng",
          detail: `Injected memory pressure via stress-ng (${memoryMb}M for ${timeoutSeconds}s)`,
          handle: {
            cleanup: async (): Promise<void> => {
              await this.commandExecutor(["pkill", "-f", "stress-ng"]);
            },
          },
        };
      }

      const fallbackCommand = [
        "dd",
        "if=/dev/zero",
        `of=${DEFAULT_MEMORY_TMPFS_FILE}`,
        "bs=1M",
        `count=${memoryMb}`,
      ];

      const fallbackResult = await this.commandExecutor(fallbackCommand);
      if (!fallbackResult.success) {
        return {
          status: "error",
          strategy: "stress-ng+tmpfs",
          detail:
            `Memory pressure injection failed. ` +
            `stress-ng: ${stressResult.stderr || stressResult.stdout || "unknown"}; ` +
            `tmpfs fallback: ${fallbackResult.stderr || fallbackResult.stdout || "unknown"}`,
        };
      }

      this.memoryArtifacts.add(DEFAULT_MEMORY_TMPFS_FILE);
      return {
        status: "active",
        strategy: "tmpfs-fill",
        detail: `Injected memory pressure by filling tmpfs (${DEFAULT_MEMORY_TMPFS_FILE})`,
        handle: {
          cleanup: async (): Promise<void> => {
            this.memoryArtifacts.delete(DEFAULT_MEMORY_TMPFS_FILE);
            await this.commandExecutor(["rm", "-f", DEFAULT_MEMORY_TMPFS_FILE]);
            await this.commandExecutor(["pkill", "-f", "stress-ng"]);
          },
        },
      };
    } catch (error) {
      return {
        status: "error",
        strategy: "memory",
        detail: `Memory pressure injection failed: ${toErrorMessage(error)}`,
      };
    }
  }

  public async injectDiskFault(
    opts: DiskFaultOptions = {},
  ): Promise<FaultInjectionResult> {
    await this.ensureDocker();

    try {
      const sizeMb = Math.max(1, Math.floor(opts.size_mb ?? DEFAULT_DISK_MB));
      const filePath = (opts.file_path ?? DEFAULT_DISK_FILE).trim() || DEFAULT_DISK_FILE;

      const fallocateCommand = ["fallocate", "-l", `${sizeMb}M`, filePath];
      const fallocateResult = await this.commandExecutor(fallocateCommand);

      if (!fallocateResult.success) {
        const ddFallback = [
          "dd",
          "if=/dev/zero",
          `of=${filePath}`,
          "bs=1M",
          `count=${sizeMb}`,
        ];
        const fallbackResult = await this.commandExecutor(ddFallback);
        if (!fallbackResult.success) {
          return {
            status: "error",
            strategy: "fallocate+dd",
            detail:
              `Disk fault injection failed. ` +
              `fallocate: ${fallocateResult.stderr || fallocateResult.stdout || "unknown"}; ` +
              `dd fallback: ${fallbackResult.stderr || fallbackResult.stdout || "unknown"}`,
          };
        }
      }

      this.diskArtifacts.add(filePath);
      return {
        status: "active",
        strategy: "fallocate",
        detail: `Injected disk exhaustion fault by allocating ${sizeMb}M at ${filePath}`,
        handle: {
          cleanup: async (): Promise<void> => {
            this.diskArtifacts.delete(filePath);
            await this.commandExecutor(["rm", "-f", filePath]);
          },
        },
      };
    } catch (error) {
      return {
        status: "error",
        strategy: "disk",
        detail: `Disk fault injection failed: ${toErrorMessage(error)}`,
      };
    }
  }

  public async clearFaults(): Promise<FaultInjectionStatus> {
    try {
      await this.cleanup();
      const inDocker = await this.isDockerEnvironment();
      if (!inDocker) {
        return {
          status: "clean",
          strategy: "guarded-noop",
          detail: "No active Docker environment detected; skipped force-clear commands",
        };
      }

      const failures: string[] = [];

      const tcCleanup = await this.commandExecutor([
        "tc",
        "qdisc",
        "del",
        "dev",
        "eth0",
        "root",
        "netem",
      ]);
      if (!tcCleanup.success && tcCleanup.exitCode !== 2) {
        failures.push(`tc cleanup failed: ${tcCleanup.stderr || tcCleanup.stdout}`);
      }

      await this.commandExecutor(["pkill", "-f", "stress-ng"]);

      const iptablesCommands = Array.from(this.iptablesCleanupCommands.entries());
      for (const [key, command] of iptablesCommands) {
        const result = await this.commandExecutor(command);
        this.iptablesCleanupCommands.delete(key);
        if (!result.success && result.exitCode !== 1) {
          failures.push(`iptables cleanup failed: ${result.stderr || result.stdout}`);
        }
      }

      const artifactPaths = new Set<string>([
        DEFAULT_DISK_FILE,
        DEFAULT_MEMORY_TMPFS_FILE,
        ...this.diskArtifacts,
        ...this.memoryArtifacts,
      ]);

      for (const path of artifactPaths) {
        await this.commandExecutor(["rm", "-f", path]);
      }
      this.diskArtifacts.clear();
      this.memoryArtifacts.clear();

      if (failures.length > 0) {
        return {
          status: "error",
          strategy: "force-cleanup",
          detail: failures.join("; "),
        };
      }

      return {
        status: "clean",
        strategy: "force-cleanup",
        detail: "Cleared tc/iptables rules, stress-ng processes, and disk artifacts",
      };
    } catch (error) {
      return {
        status: "error",
        strategy: "force-cleanup",
        detail: `Failed clearing chaos faults: ${toErrorMessage(error)}`,
      };
    }
  }

  public async inject(
    type: ChaosType,
    target: string,
    options: ChaosOptions = {},
  ): Promise<void> {
    await this.runExclusive(async () => {
      if (getNodeEnv() === "production") {
        this.state = "error";
        throw new Error("Chaos injection blocked in production");
      }

      const durationMs = normalizeDuration(options.duration_ms);
      const resolvedTarget = normalizeTarget(target, options.target);

      this.state = "active";
      const effectId = `${Date.now()}-${this.sequence}`;
      this.sequence += 1;

      try {
        const handle = await this.runtime.apply(type, resolvedTarget);
        const active: ActiveEffect = {
          id: effectId,
          handle,
          timer: null,
        };

        active.timer = this.setTimer(() => {
          void this.expireEffect(effectId);
        }, durationMs);

        this.activeEffects.set(effectId, active);
      } catch (error) {
        this.state = "error";
        throw error;
      }
    });
  }

  public async cleanup(): Promise<void> {
    await this.runExclusive(async () => {
      const failures: string[] = [];

      const effects = Array.from(this.activeEffects.values());
      for (const effect of effects) {
        try {
          await this.cleanupEffect(effect);
        } catch (error) {
          const message =
            error instanceof Error ? error.message : String(error);
          failures.push(`${effect.id}: ${message}`);
        }
      }

      if (failures.length > 0) {
        this.state = "error";
        throw new Error(`Failed chaos cleanup: ${failures.join("; ")}`);
      }

      this.state = "clean";
    });
  }

  public status(): ChaosStatus {
    if (this.activeEffects.size > 0) {
      return "active";
    }

    return this.state;
  }

  private async expireEffect(effectId: string): Promise<void> {
    await this.runExclusive(async () => {
      const effect = this.activeEffects.get(effectId);
      if (!effect) {
        return;
      }

      try {
        await this.cleanupEffect(effect);
      } catch {
        this.state = "error";
        return;
      }

      if (this.activeEffects.size === 0) {
        this.state = "clean";
      }
    });
  }

  private async cleanupEffect(effect: ActiveEffect): Promise<void> {
    this.activeEffects.delete(effect.id);
    if (effect.timer !== null) {
      this.clearTimer(effect.timer);
      effect.timer = null;
    }
    await effect.handle.cleanup();
  }

  private async runExclusive(action: () => Promise<void>): Promise<void> {
    const next = this.queue.then(action);
    this.queue = next.catch(() => undefined);
    return await next;
  }

  private async applyBuiltInChaos(
    type: ChaosType,
    _target: string,
  ): Promise<ChaosEffectHandle> {
    let result: FaultInjectionResult;

    switch (type) {
      case "network-partition": {
        result = await this.injectNetworkFault({ delay_ms: 0, loss_pct: 100 });
        break;
      }
      case "slow-network": {
        result = await this.injectNetworkFault({ delay_ms: 250, loss_pct: 5 });
        break;
      }
      case "broken-pipe": {
        result = await this.injectNetworkFault({ delay_ms: 0, loss_pct: 100 });
        break;
      }
      case "malformed-json": {
        result = await this.injectNetworkFault({ delay_ms: 50, loss_pct: 10 });
        break;
      }
      case "memory-pressure": {
        result = await this.injectMemoryPressure({
          memory_mb: DEFAULT_MEMORY_MB,
          timeout_s: DEFAULT_MEMORY_TIMEOUT_SECONDS,
        });
        break;
      }
      case "disk-exhaustion": {
        result = await this.injectDiskFault({
          size_mb: DEFAULT_DISK_MB,
          file_path: DEFAULT_DISK_FILE,
        });
        break;
      }
      default: {
        result = {
          status: "error",
          detail: `Unsupported chaos type: ${type}`,
        };
      }
    }

    if (result.status === "error" || !result.handle) {
      throw new Error(result.detail);
    }

    return result.handle;
  }

  private async ensureDocker(): Promise<void> {
    const inDocker = await this.isDockerEnvironment();
    if (!inDocker) {
      throw new Error(
        "Chaos fault injection is Docker-only. Detected host environment; refusing to mutate host networking/resources.",
      );
    }
  }

  private async isDockerEnvironment(): Promise<boolean> {
    if (await this.fileExists("/.dockerenv")) {
      return true;
    }

    try {
      const cgroup = await this.readFile("/proc/1/cgroup");
      const lowered = cgroup.toLowerCase();
      return (
        lowered.includes("docker") ||
        lowered.includes("containerd") ||
        lowered.includes("kubepods")
      );
    } catch {
      return false;
    }
  }
}

export const createChaosInjector = /* @__PURE__ */ (
  config: ChaosInjectorConfig = {},
): ChaosInjector => new ChaosInjector(config);
