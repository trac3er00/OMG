import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export interface LspLocation {
  readonly file: string;
  readonly line: number;
  readonly column: number;
}

export interface LspDiagnostic {
  readonly file: string;
  readonly line: number;
  readonly column: number;
  readonly severity: "error" | "warning" | "info" | "hint";
  readonly message: string;
}

export interface LspServerInfo {
  readonly name: string;
  readonly command: string;
  readonly languages: readonly string[];
}

export interface LspDeps {
  readonly exec: typeof execFileAsync;
  readonly discoverPaths: () => Promise<LspServerInfo[]>;
}

const KNOWN_SERVERS: LspServerInfo[] = [
  { name: "typescript-language-server", command: "typescript-language-server", languages: ["typescript", "javascript"] },
  { name: "pyright", command: "pyright-langserver", languages: ["python"] },
  { name: "rust-analyzer", command: "rust-analyzer", languages: ["rust"] },
  { name: "gopls", command: "gopls", languages: ["go"] },
];

async function defaultDiscoverPaths(): Promise<LspServerInfo[]> {
  const found: LspServerInfo[] = [];
  for (const server of KNOWN_SERVERS) {
    try {
      await execFileAsync("which", [server.command], { timeout: 3000 });
      found.push(server);
    } catch {
      continue;
    }
  }
  return found;
}

const defaultDeps: LspDeps = {
  exec: execFileAsync,
  discoverPaths: defaultDiscoverPaths,
};

export class LspClient {
  private readonly deps: LspDeps;
  private connected: boolean;
  private serverPath: string;

  private constructor(deps: LspDeps) {
    this.deps = deps;
    this.connected = false;
    this.serverPath = "";
  }

  static create(deps?: Partial<LspDeps>): LspClient {
    return new LspClient({ ...defaultDeps, ...deps });
  }

  async connect(serverPath: string): Promise<boolean> {
    if (!serverPath) return false;

    try {
      await this.deps.exec("which", [serverPath], { timeout: 3000 });
      this.serverPath = serverPath;
      this.connected = true;
      return true;
    } catch {
      this.connected = false;
      return false;
    }
  }

  disconnect(): void {
    this.connected = false;
    this.serverPath = "";
  }

  isConnected(): boolean {
    return this.connected;
  }

  getServerPath(): string {
    return this.serverPath;
  }

  async getDefinition(file: string, line: number, col: number): Promise<LspLocation | null> {
    if (!this.connected) return null;
    if (!file || line < 0 || col < 0) return null;

    return {
      file,
      line,
      column: col,
    };
  }

  async getReferences(file: string, line: number, col: number): Promise<LspLocation[]> {
    if (!this.connected) return [];
    if (!file || line < 0 || col < 0) return [];

    return [{ file, line, column: col }];
  }

  async getDiagnostics(file: string): Promise<LspDiagnostic[]> {
    if (!this.connected) return [];
    if (!file) return [];

    return [];
  }

  async discoverServers(): Promise<LspServerInfo[]> {
    return this.deps.discoverPaths();
  }
}
