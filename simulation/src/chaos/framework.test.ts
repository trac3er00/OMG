import { describe, expect, it } from "bun:test";
import { ChaosInjector } from "./framework.ts";

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

interface MockCommandResult {
  readonly success: boolean;
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
}

function okResult(overrides: Partial<MockCommandResult> = {}): MockCommandResult {
  return {
    success: true,
    exitCode: 0,
    stdout: "",
    stderr: "",
    ...overrides,
  };
}

describe("ChaosInjector", () => {
  it("blocks chaos injection in production", async () => {
    const env = (
      globalThis as {
        process?: {
          env?: Record<string, string | undefined>;
        };
      }
    ).process?.env;

    if (!env) {
      return;
    }

    const previous = env.NODE_ENV;
    env.NODE_ENV = "production";

    const chaos = new ChaosInjector();
    await expect(
      chaos.inject("slow-network", "target-api", {}),
    ).rejects.toThrow("Chaos injection blocked in production");

    if (previous === undefined) {
      delete env.NODE_ENV;
      return;
    }

    env.NODE_ENV = previous;
  });

  it("enforces max duration of 60s", async () => {
    const chaos = new ChaosInjector();

    await expect(
      chaos.inject("network-partition", "worker-a", { duration_ms: 60_001 }),
    ).rejects.toThrow("exceeds max 60000ms");
  });

  it("throws docker-only guard when not running in Docker", async () => {
    const chaos = new ChaosInjector({
      fileExists: async () => false,
      readFile: async () => "0::/",
      commandExecutor: async () => okResult(),
    });

    await expect(
      chaos.inject("slow-network", "worker-a", { duration_ms: 1000 }),
    ).rejects.toThrow("Docker-only");
  });

  it("injects network fault using tc netem and clears it on cleanup", async () => {
    const commands: string[][] = [];
    const chaos = new ChaosInjector({
      fileExists: async (path) => path === "/.dockerenv",
      readFile: async () => "",
      commandExecutor: async (command) => {
        commands.push([...command]);
        return okResult();
      },
    });

    await chaos.inject("slow-network", "svc-a", { duration_ms: 1000 });
    await chaos.cleanup();

    const hasTcAdd = commands.some(
      (command) =>
        command.join(" ") ===
        "tc qdisc add dev eth0 root netem delay 250ms loss 5%",
    );
    const hasTcDel = commands.some(
      (command) =>
        command.join(" ") === "tc qdisc del dev eth0 root netem",
    );

    expect(hasTcAdd).toBe(true);
    expect(hasTcDel).toBe(true);
  });

  it("falls back to iptables when tc is unavailable", async () => {
    const commands: string[][] = [];
    const chaos = new ChaosInjector({
      fileExists: async (path) => path === "/.dockerenv",
      readFile: async () => "",
      commandExecutor: async (command) => {
        commands.push([...command]);
        if (command[0] === "tc" && command[1] === "qdisc" && command[2] === "add") {
          return okResult({
            success: false,
            exitCode: 1,
            stderr: "tc not found",
          });
        }
        return okResult();
      },
    });

    const result = await chaos.injectNetworkFault({ delay_ms: 10, loss_pct: 30 });
    expect(result.status).toBe("active");
    expect(result.strategy).toBe("iptables-drop");

    await result.handle?.cleanup();

    const hasIptablesAdd = commands.some(
      (command) => command.slice(0, 3).join(" ") === "iptables -A OUTPUT",
    );
    const hasIptablesDel = commands.some(
      (command) => command.slice(0, 3).join(" ") === "iptables -D OUTPUT",
    );

    expect(hasIptablesAdd).toBe(true);
    expect(hasIptablesDel).toBe(true);
  });

  it("clearFaults force-clears memory and disk artifacts", async () => {
    const commands: string[][] = [];
    const chaos = new ChaosInjector({
      fileExists: async (path) => path === "/.dockerenv",
      readFile: async () => "docker",
      commandExecutor: async (command) => {
        commands.push([...command]);
        return okResult();
      },
    });

    await chaos.inject("memory-pressure", "svc-mem", { duration_ms: 1000 });
    await chaos.inject("disk-exhaustion", "svc-disk", { duration_ms: 1000 });

    const clearResult = await chaos.clearFaults();
    expect(clearResult.status).toBe("clean");

    const hasPkill = commands.some(
      (command) => command.join(" ") === "pkill -f stress-ng",
    );
    const hasDiskRemove = commands.some(
      (command) => command.join(" ") === "rm -f /tmp/chaos-disk",
    );

    expect(hasPkill).toBe(true);
    expect(hasDiskRemove).toBe(true);
  });

  it("defaults timeout to 60000ms when duration is omitted", async () => {
    let scheduledMs = 0;
    const cleanupCalls: string[] = [];

    const chaos = new ChaosInjector({
      runtime: {
        async apply(_type, target) {
          return {
            async cleanup(): Promise<void> {
              cleanupCalls.push(target);
            },
          };
        },
      },
      setTimer(callback, delayMs) {
        scheduledMs = delayMs;
        return { callback, delayMs };
      },
      clearTimer() {
        return;
      },
    });

    await chaos.inject("malformed-json", "api-gateway", {});

    expect(scheduledMs).toBe(60_000);
    expect(chaos.status()).toBe("active");

    await chaos.cleanup();
    expect(cleanupCalls).toEqual(["api-gateway"]);
    expect(chaos.status()).toBe("clean");
  });

  it("auto-cleans active chaos after duration", async () => {
    const cleanupCalls: string[] = [];
    const chaos = new ChaosInjector({
      runtime: {
        async apply(_type, target) {
          return {
            async cleanup(): Promise<void> {
              cleanupCalls.push(target);
            },
          };
        },
      },
    });

    await chaos.inject("slow-network", "test-service", { duration_ms: 30 });
    expect(chaos.status()).toBe("active");

    await delay(90);

    expect(cleanupCalls).toEqual(["test-service"]);
    expect(chaos.status()).toBe("clean");
  });

  it("cleanup removes all chaos effects", async () => {
    const cleanupCalls: string[] = [];
    const chaos = new ChaosInjector({
      runtime: {
        async apply(type, target) {
          return {
            async cleanup(): Promise<void> {
              cleanupCalls.push(`${type}:${target}`);
            },
          };
        },
      },
    });

    await chaos.inject("slow-network", "svc-a", { duration_ms: 1000 });
    await chaos.inject("broken-pipe", "svc-b", { duration_ms: 1000 });

    expect(chaos.status()).toBe("active");

    await chaos.cleanup();

    expect(cleanupCalls).toHaveLength(2);
    expect(cleanupCalls.includes("slow-network:svc-a")).toBe(true);
    expect(cleanupCalls.includes("broken-pipe:svc-b")).toBe(true);
    expect(chaos.status()).toBe("clean");
  });
});
