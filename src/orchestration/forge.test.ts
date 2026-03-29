import { describe, expect, test } from "bun:test";
import { ForgeSystem, type ForgeJob } from "./forge.js";

describe("ForgeSystem", () => {
  test("routes cybersecurity domain to forge-cybersecurity", () => {
    const forge = ForgeSystem.create();
    const job: ForgeJob = {
      id: "job-1",
      domain: "cybersecurity",
      task: "run hardening checks",
      status: "pending",
    };

    const dispatched = forge.submit(job);
    expect(dispatched.agent).toBe("forge-cybersecurity");
    expect(dispatched.status).toBe("queued");
  });

  test("routes code domain to forge-code", () => {
    const forge = ForgeSystem.create();
    const job: ForgeJob = {
      id: "job-2",
      domain: " code ",
      task: "implement feature",
      status: "pending",
    };

    const dispatched = forge.submit(job);
    expect(dispatched.domain).toBe("code");
    expect(dispatched.agent).toBe("forge-code");
  });

  test("throws for invalid domain with valid domain list", () => {
    const forge = ForgeSystem.create();
    const job: ForgeJob = {
      id: "job-3",
      domain: "finance",
      task: "audit",
      status: "pending",
    };

    expect(() => forge.submit(job)).toThrow(/Unknown domain: finance/);
    expect(() => forge.submit(job)).toThrow(/Valid domains:/);
    expect(() => forge.submit(job)).toThrow(/cybersecurity/);
    expect(() => forge.submit(job)).toThrow(/code/);
  });
});
