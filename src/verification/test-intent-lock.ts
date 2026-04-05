import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";

export interface TestEvidence {
  readonly file: string;
  readonly passed: boolean;
}

export interface WriteAllowedResult {
  readonly allowed: boolean;
  readonly reason: string;
}

export interface LockState {
  readonly locked: boolean;
  readonly runId?: string;
  readonly lockedAt?: string;
}

export function resolveTestFile(sourceFile: string): string {
  return sourceFile.replace(/\.(ts|js|tsx|jsx)$/, ".test.$1");
}

export class TestIntentLock {
  private readonly lockPath: string;

  constructor(projectDir: string) {
    const resolver = new StateResolver(projectDir);
    this.lockPath = resolver.resolve("test-intent-lock.json");
  }

  isLocked(): boolean {
    const state = readJsonFile<LockState>(this.lockPath);
    return state?.locked === true;
  }

  lockState(): LockState {
    const state = readJsonFile<LockState>(this.lockPath);
    if (!state) {
      return { locked: false };
    }
    return state;
  }

  acquire(runId: string): void {
    const state: LockState = {
      locked: true,
      runId,
      lockedAt: new Date().toISOString(),
    };
    atomicWriteJson(this.lockPath, state);
  }

  release(runId: string): void {
    const current = readJsonFile<LockState>(this.lockPath);
    if (current?.runId === runId) {
      const state: LockState = { locked: false };
      atomicWriteJson(this.lockPath, state);
    }
  }

  checkWriteAllowed(
    sourceFile: string,
    testEvidence: readonly TestEvidence[],
  ): WriteAllowedResult {
    if (!this.isLocked()) {
      return { allowed: true, reason: "TDD lock is not active" };
    }

    const testFile = resolveTestFile(sourceFile);
    const stem = sourceFile.replace(/\.[^.]+$/, "").split("/").pop() ?? "";

    const relevantTest = testEvidence.find(
      (e) =>
        e.file === testFile ||
        (stem && e.file.includes(stem)),
    );

    if (!relevantTest) {
      return {
        allowed: false,
        reason: `No test evidence for ${sourceFile} — write requires ${testFile} to pass first`,
      };
    }

    if (!relevantTest.passed) {
      return {
        allowed: false,
        reason: `Test ${relevantTest.file} is failing — fix tests before writing source`,
      };
    }

    return {
      allowed: true,
      reason: `Passing test evidence found: ${relevantTest.file}`,
    };
  }
}
