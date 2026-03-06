import { ControlPlaneService } from "./service.ts";

type RouteHandler = (payload: Record<string, unknown>) => readonly [number, unknown];

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: { "content-type": "application/json" }
  });
}

function parseJson(request: Request): Promise<Record<string, unknown>> {
  return request
    .json()
    .then((value) => ((value && typeof value === "object" && !Array.isArray(value) ? value : {}) as Record<string, unknown>))
    .catch(() => ({}));
}

export function createFetchHandler(service = new ControlPlaneService()) {
  const routes = new Map<string, RouteHandler>([
    ["/v1/policy/evaluate", (payload) => service.policyEvaluate(payload)],
    ["/v1/trust/review", (payload) => service.trustReview(payload)],
    ["/v1/evidence/ingest", (payload) => service.evidenceIngest(payload)],
    ["/v1/runtime/dispatch", (payload) => service.runtimeDispatch(payload)],
    ["/v1/registry/verify", (payload) => service.registryVerify(payload)],
    ["/v1/lab/jobs", (payload) => service.labJobs(payload)]
  ]);

  return async function fetch(request: Request) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/v1/scoreboard/baseline") {
      const [status, payload] = service.scoreboardBaseline();
      return jsonResponse(payload, status);
    }

    if (request.method !== "POST") {
      return jsonResponse({ status: "error", message: "Not found" }, 404);
    }

    const handler = routes.get(url.pathname);
    if (!handler) {
      return jsonResponse({ status: "error", message: "Not found" }, 404);
    }

    const payload = await parseJson(request);
    const [status, body] = handler(payload);
    return jsonResponse(body, status);
  };
}

export function runServer(options: { host?: string; port?: number; projectDir?: string } = {}) {
  const host = options.host || "127.0.0.1";
  const port = options.port || 8787;
  const service = new ControlPlaneService(options.projectDir);
  return Bun.serve({
    hostname: host,
    port,
    fetch: createFetchHandler(service)
  });
}

function parseArgs(argv: string[]) {
  const out: { host?: string; port?: number; projectDir?: string } = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];
    if (arg === "--host" && value) {
      out.host = value;
      index += 1;
    } else if (arg === "--port" && value) {
      out.port = Number(value);
      index += 1;
    } else if (arg === "--project-dir" && value) {
      out.projectDir = value;
      index += 1;
    }
  }
  return out;
}

if (import.meta.main) {
  const options = parseArgs(process.argv.slice(2));
  if (options.host && options.host !== "127.0.0.1") {
    process.stderr.write(
      `WARNING: binding to ${options.host} exposes the control plane to the network without authentication.\n`
    );
  }
  runServer(options);
}
