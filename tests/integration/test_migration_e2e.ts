import { test, expect } from "bun:test";
import { CONFIG_MIGRATION_STEPS as MIGRATION_STEPS } from "../../src/config/migration.js";

type MigrationStep = {
  readonly from: string;
  readonly to: string;
  readonly steps: readonly {
    readonly action: string;
    readonly path: string;
    readonly value: unknown;
  }[];
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function setAtPath(target: Record<string, unknown>, path: string, value: unknown) {
  const keys = path.split(".");
  let cursor: Record<string, unknown> = target;
  for (let i = 0; i < keys.length - 1; i += 1) {
    const key = keys[i]!;
    const current = cursor[key];
    if (typeof current !== "object" || current === null || Array.isArray(current)) {
      cursor[key] = {};
    }
    cursor = cursor[key] as Record<string, unknown>;
  }
  cursor[keys[keys.length - 1]!] = value;
}

function applyMigrationChain(
  input: Record<string, unknown>,
  chain: readonly MigrationStep[],
): Record<string, unknown> {
  return chain.reduce<Record<string, unknown>>((config, step) => {
    const next = clone(config);
    for (const migration of step.steps) {
      if (migration.action === "add_config") {
        setAtPath(next, migration.path, clone(migration.value));
      }
    }
    next.version = step.to;
    return next;
  }, clone(input));
}

test("migration: 2.3.0 to 2.5.0 step exists", () => {
  expect(Array.isArray(MIGRATION_STEPS)).toBe(true);
  const step = MIGRATION_STEPS.find((entry) => entry.from === "2.3.0" && entry.to === "2.5.0");
  expect(step).toBeDefined();
  expect(step?.steps.length).toBeGreaterThan(0);
});

test("migration: all version bumps recorded", () => {
  const versions = ["2.3.0", "2.5.0", "2.7.0", "2.9.0", "3.0.0-rc"];
  for (const v of versions) {
    expect(v).toMatch(/^\d+\.\d+\.\d+(-\w+)?$/);
  }
});

test("migration: v2.3.0 config migrates successfully", () => {
  const chain = ["2.3.0", "2.5.0", "2.7.0", "2.9.0", "3.0.0-rc"].map((from, index, versions) => {
    const to = versions[index + 1];
    if (!to) {
      return null;
    }
    const step = MIGRATION_STEPS.find((entry) => entry.from === from && entry.to === to);
    expect(step).toBeDefined();
    return step!;
  }).filter((step): step is MigrationStep => step !== null);

  const oldConfig = {
    version: "2.3.0",
    memory: {},
    features: {},
  };

  const migratedConfig = applyMigrationChain(oldConfig, chain);

  expect(migratedConfig.version).toBe("3.0.0-rc");
  expect(migratedConfig.memory).toHaveProperty("tiers");
  expect((migratedConfig.memory as Record<string, unknown>).tiers).toHaveProperty("auto");
  expect((migratedConfig.memory as Record<string, unknown>).tiers).toHaveProperty("micro");
  expect((migratedConfig.memory as Record<string, unknown>).tiers).toHaveProperty("ship");
  expect((migratedConfig.features as Record<string, unknown>).pause_continue).toBe(false);
  expect((migratedConfig.features as Record<string, unknown>).context_durability).toBe(false);
  expect((migratedConfig.features as Record<string, unknown>).society_of_thought).toBe(false);
  expect((migratedConfig.features as Record<string, unknown>).wave_optimization).toBe(true);
  expect((migratedConfig.features as Record<string, unknown>).cross_model_escalation).toBe(true);
  expect((migratedConfig.features as Record<string, unknown>).planning_context_retention).toBe(true);
  expect((migratedConfig.features as Record<string, unknown>).traceability).toBe(true);
  expect((migratedConfig.features as Record<string, unknown>).eval_driven_pipeline).toBe(true);
  expect((migratedConfig.features as Record<string, unknown>).smart_task_handling).toBe(true);
  expect((migratedConfig.features as Record<string, unknown>).trajectory_tracking).toBe(true);
  expect((migratedConfig.features as Record<string, unknown>).autoresearch_daemon).toEqual({
    enabled: true,
    security_envelope: true,
  });
  expect((migratedConfig.provider_registry as Record<string, unknown>).confirmed).toContain("saas");
  expect((migratedConfig.provider_registry as Record<string, unknown>).pending_stubs).toContain("bot");
  expect((migratedConfig.validation as Record<string, unknown>).domain_pack_validation).toBe(true);
  expect((migratedConfig.governance as Record<string, unknown>).enforcement_mode).toBe("soft-block");
  expect((migratedConfig.platform as Record<string, unknown>).compatibility_checks).toBe(true);
});

test("migration: migrated config is valid", () => {
  const migratedConfig = {
    version: "3.0.0-rc",
    memory: { tiers: { auto: {}, micro: {}, ship: {} } },
    features: { pause_continue: false },
  };

  expect(migratedConfig.version).toBe("3.0.0-rc");
  expect(Object.keys(migratedConfig.memory.tiers)).toContain("auto");
  expect(Object.keys(migratedConfig.memory.tiers)).toContain("micro");
  expect(Object.keys(migratedConfig.memory.tiers)).toContain("ship");
});
