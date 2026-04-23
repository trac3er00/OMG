import { describe, expect, it, beforeEach, afterEach } from "bun:test";
import { COMMANDS, showHelp, handleTuiCommand, TUI_VERSION } from "./index.js";

function captureOutput(fn: () => void): { stdout: string[]; stderr: string[] } {
  const stdout: string[] = [];
  const stderr: string[] = [];
  const originalLog = console.log;
  const originalError = console.error;

  console.log = (...args: unknown[]) => {
    stdout.push(args.map(String).join(" "));
  };
  console.error = (...args: unknown[]) => {
    stderr.push(args.map(String).join(" "));
  };

  try {
    fn();
  } finally {
    console.log = originalLog;
    console.error = originalError;
  }

  return { stdout, stderr };
}

async function captureAsyncOutput(
  fn: () => Promise<void>,
): Promise<{ stdout: string[]; stderr: string[] }> {
  const stdout: string[] = [];
  const stderr: string[] = [];
  const originalLog = console.log;
  const originalError = console.error;

  console.log = (...args: unknown[]) => {
    stdout.push(args.map(String).join(" "));
  };
  console.error = (...args: unknown[]) => {
    stderr.push(args.map(String).join(" "));
  };

  try {
    await fn();
  } finally {
    console.log = originalLog;
    console.error = originalError;
  }

  return { stdout, stderr };
}

describe("COMMANDS registry", () => {
  it("contains exactly 5 commands", () => {
    const commandNames = Object.keys(COMMANDS);
    expect(commandNames).toHaveLength(5);
    expect(commandNames).toContain("instant");
    expect(commandNames).toContain("ship");
    expect(commandNames).toContain("proof");
    expect(commandNames).toContain("blocked");
    expect(commandNames).toContain("help");
  });

  it("all commands have name and description", () => {
    for (const [key, info] of Object.entries(COMMANDS)) {
      expect(info.name).toBe(key);
      expect(typeof info.description).toBe("string");
      expect(info.description.length).toBeGreaterThan(0);
    }
  });
});

describe("showHelp", () => {
  it("shows exactly 5 commands in output", () => {
    const { stdout } = captureOutput(showHelp);
    const output = stdout.join("\n");

    expect(output).toContain("instant");
    expect(output).toContain("ship");
    expect(output).toContain("proof");
    expect(output).toContain("blocked");
    expect(output).toContain("help");
    expect(output).toContain(`omg-tui v${TUI_VERSION}`);
  });

  it("shows usage and examples", () => {
    const { stdout } = captureOutput(showHelp);
    const output = stdout.join("\n");

    expect(output).toContain("Usage:");
    expect(output).toContain("Commands:");
    expect(output).toContain("Examples:");
  });
});

describe("handleTuiCommand", () => {
  let exitCode: number | undefined;
  const originalExit = process.exit;

  beforeEach(() => {
    exitCode = undefined;
    process.exit = ((code?: number) => {
      exitCode = code ?? 0;
      throw new Error(`process.exit(${exitCode})`);
    }) as typeof process.exit;
  });

  afterEach(() => {
    process.exit = originalExit;
  });

  it("help command shows all 5 commands", async () => {
    const { stdout } = await captureAsyncOutput(() =>
      handleTuiCommand(["help"]),
    );
    const output = stdout.join("\n");

    expect(output).toContain("instant");
    expect(output).toContain("ship");
    expect(output).toContain("proof");
    expect(output).toContain("blocked");
    expect(output).toContain("help");
  });

  it("--help flag shows help", async () => {
    const { stdout } = await captureAsyncOutput(() =>
      handleTuiCommand(["--help"]),
    );
    const output = stdout.join("\n");

    expect(output).toContain("Commands:");
  });

  it("-v flag shows version", async () => {
    const { stdout } = await captureAsyncOutput(() => handleTuiCommand(["-v"]));
    const output = stdout.join("\n");

    expect(output).toContain(`omg-tui v${TUI_VERSION}`);
  });

  it("unknown command shows help and exits with code 1", async () => {
    let caught = false;
    try {
      await captureAsyncOutput(() => handleTuiCommand(["unknowncommand123"]));
    } catch {
      caught = true;
    }

    expect(caught).toBe(true);
    expect(exitCode).toBe(1);
  });

  it("default command (no args) shows help", async () => {
    const { stdout } = await captureAsyncOutput(() => handleTuiCommand([]));
    const output = stdout.join("\n");

    expect(output).toContain("Commands:");
  });
});

describe("command routing", () => {
  let exitCode: number | undefined;
  const originalExit = process.exit;

  beforeEach(() => {
    exitCode = undefined;
    process.exit = ((code?: number) => {
      exitCode = code ?? 0;
      throw new Error(`process.exit(${exitCode})`);
    }) as typeof process.exit;
  });

  afterEach(() => {
    process.exit = originalExit;
  });

  it("instant handler exists and is callable", () => {
    const instantInfo = COMMANDS["instant"];
    expect(instantInfo).toBeDefined();
    expect(typeof instantInfo.handler).toBe("function");
  });

  it("ship handler exists and is callable", () => {
    const shipInfo = COMMANDS["ship"];
    expect(shipInfo).toBeDefined();
    expect(typeof shipInfo.handler).toBe("function");
  });

  it("proof handler exists and is callable", () => {
    const proofInfo = COMMANDS["proof"];
    expect(proofInfo).toBeDefined();
    expect(typeof proofInfo.handler).toBe("function");
  });

  it("blocked handler exists and is callable", () => {
    const blockedInfo = COMMANDS["blocked"];
    expect(blockedInfo).toBeDefined();
    expect(typeof blockedInfo.handler).toBe("function");
  });

  it("help handler is null (handled inline)", () => {
    const helpInfo = COMMANDS["help"];
    expect(helpInfo).toBeDefined();
    expect(helpInfo.handler).toBeNull();
  });

  it("instant without prompt exits with code 1", async () => {
    let caught = false;
    try {
      await captureAsyncOutput(() => handleTuiCommand(["instant"]));
    } catch {
      caught = true;
    }

    expect(caught).toBe(true);
    expect(exitCode).toBe(1);
  });
});
