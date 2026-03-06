import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ControlPlaneService } from "../control_plane/service.ts";
import { createFetchHandler } from "../control_plane/server.ts";

describe("ControlPlaneService", () => {
  const projectDir = mkdtempSync(join(tmpdir(), "omg-control-plane-"));
  const service = new ControlPlaneService(projectDir);

  afterAll(() => {
    rmSync(projectDir, { recursive: true, force: true });
  });

  test("evaluates bash policy", () => {
    const [status, payload] = service.policyEvaluate({ tool: "Bash", input: { command: "echo hello" } });
    expect(status).toBe(200);
    expect((payload as any).action).toBe("allow");
  });

  test("writes evidence packs", () => {
    const [status, payload] = service.evidenceIngest({
      run_id: "run-1",
      tests: [],
      security_scans: [],
      diff_summary: {},
      reproducibility: {},
      unresolved_risks: []
    });
    expect(status).toBe(202);
    expect(payload.status).toBe("accepted");
    const written = JSON.parse(readFileSync(join(projectDir, ".omg", "evidence", "run-1.json"), "utf8"));
    expect(written.run_id).toBe("run-1");
  });

  test("runs lab jobs", () => {
    const [status, payload] = service.labJobs({
      dataset: { license: "MIT", source: "internal" },
      base_model: { source: "partner", allow_distill: true }
    });
    expect(status).toBe(201);
    expect(payload.status).toBe("ready");
  });
});

describe("control plane server", () => {
  let server: ReturnType<typeof Bun.serve> | null = null;

  beforeAll(() => {
    server = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch: createFetchHandler(new ControlPlaneService())
    });
  });

  afterAll(() => {
    server?.stop(true);
  });

  test("serves scoreboard baseline", async () => {
    const response = await fetch(`${server!.url}v1/scoreboard/baseline`);
    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.target_policy).toBe("non-regression-or-better");
  });
});
