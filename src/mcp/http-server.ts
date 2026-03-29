import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { isIP } from "node:net";
import { validateToken, type JwtPayload } from "../security/jwt-auth.js";

const DEFAULT_PORT = 8787;
const DEFAULT_HOST = "127.0.0.1";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);

export interface AuthenticatedRequest {
  readonly request: IncomingMessage;
  readonly payload: JwtPayload;
  readonly body: unknown;
}

export interface HttpControlPlaneOptions {
  readonly port?: number;
  readonly host?: string;
  readonly unsafe?: boolean;
  readonly jwtPublicKey: string | Buffer;
  readonly handler?: (request: AuthenticatedRequest) => Promise<unknown>;
}

export class HttpControlPlaneServer {
  private readonly options: Required<Omit<HttpControlPlaneOptions, "handler">> & Pick<HttpControlPlaneOptions, "handler">;
  private server: Server | null = null;

  private constructor(options: HttpControlPlaneOptions) {
    const host = options.host ?? DEFAULT_HOST;
    if (!this.isLoopback(host) && options.unsafe !== true) {
      throw new Error("Non-loopback binding requires --unsafe");
    }

    this.options = {
      port: options.port ?? DEFAULT_PORT,
      host,
      unsafe: options.unsafe ?? false,
      jwtPublicKey: options.jwtPublicKey,
      ...(options.handler ? { handler: options.handler } : {}),
    };
  }

  static create(options: HttpControlPlaneOptions): HttpControlPlaneServer {
    return new HttpControlPlaneServer(options);
  }

  async start(): Promise<void> {
    if (this.server) {
      return;
    }

    this.server = createServer(async (req, res) => {
      await this.route(req, res);
    });

    await new Promise<void>((resolve, reject) => {
      if (!this.server) {
        reject(new Error("server not initialized"));
        return;
      }

      this.server.once("error", reject);
      this.server.listen(this.options.port, this.options.host, () => {
        this.server?.off("error", reject);
        resolve();
      });
    });
  }

  async stop(): Promise<void> {
    if (!this.server) {
      return;
    }

    const server = this.server;
    this.server = null;

    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }

  private async route(req: IncomingMessage, res: ServerResponse): Promise<void> {
    if (req.url === "/health" && req.method === "GET") {
      this.respond(res, 200, { ok: true, service: "omg-control-plane" });
      return;
    }

    const authHeader = req.headers.authorization;
    if (!authHeader?.startsWith("Bearer ")) {
      this.respond(res, 401, { error: "Missing bearer token" });
      return;
    }

    const token = authHeader.slice("Bearer ".length).trim();
    const validation = validateToken(token, this.options.jwtPublicKey);
    if (!validation.valid || !validation.payload) {
      this.respond(res, 401, { error: validation.error ?? "Unauthorized" });
      return;
    }

    const body = await this.readJsonBody(req);

    if (!this.options.handler) {
      this.respond(res, 200, {
        ok: true,
        path: req.url ?? "/",
        role: validation.payload.role,
      });
      return;
    }

    try {
      const result = await this.options.handler({
        request: req,
        payload: validation.payload,
        body,
      });
      this.respond(res, 200, result);
    } catch (error) {
      this.respond(res, 500, {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async readJsonBody(req: IncomingMessage): Promise<unknown> {
    const chunks: Buffer[] = [];
    for await (const chunk of req) {
      if (typeof chunk === "string") {
        chunks.push(Buffer.from(chunk, "utf8"));
      } else {
        chunks.push(chunk);
      }
    }

    if (chunks.length === 0) {
      return {};
    }

    const text = Buffer.concat(chunks).toString("utf8").trim();
    if (!text) {
      return {};
    }

    return JSON.parse(text) as unknown;
  }

  private respond(res: ServerResponse, statusCode: number, payload: unknown): void {
    const body = JSON.stringify(payload);
    res.writeHead(statusCode, {
      "content-type": "application/json; charset=utf-8",
      "content-length": Buffer.byteLength(body).toString(),
    });
    res.end(body);
  }

  private isLoopback(host: string): boolean {
    if (LOOPBACK_HOSTS.has(host)) {
      return true;
    }

    const ipVersion = isIP(host);
    if (ipVersion === 4) {
      return host.startsWith("127.");
    }
    if (ipVersion === 6) {
      return host === "::1";
    }

    return false;
  }
}

export function parseUnsafeFlag(args: readonly string[]): boolean {
  return args.includes("--unsafe");
}
