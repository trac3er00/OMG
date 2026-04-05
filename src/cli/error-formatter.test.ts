import { describe, expect, it } from "bun:test";
import { formatCliError, printCliError } from "./error-formatter";

const cases: Array<{ name: string; error: unknown; message: string; suggestion: string; exitCode?: number }> = [
  {
    name: "maps MCP server missing",
    error: new Error("MCP server not found: omg-control"),
    message: "Required MCP server is missing.",
    suggestion: "Run `npx omg install --apply`.",
  },
  {
    name: "maps ENOENT .omg path",
    error: "ENOENT: no such file or directory, open '.omg/config.json'",
    message: "OMG environment files are missing.",
    suggestion: "Run `npx omg install --apply` to initialize.",
  },
  {
    name: "maps bun not found",
    error: "bun: not found",
    message: "Bun is not installed.",
    suggestion: "Install Bun: curl -fsSL https://bun.sh/install | bash",
  },
  {
    name: "maps permission denied",
    error: new Error("permission denied"),
    message: "Permission denied.",
    suggestion: "Check file permissions or run with appropriate user.",
  },
  {
    name: "maps port in use",
    error: "EADDRINUSE: address already in use",
    message: "Port already in use.",
    suggestion: "Check if another omg process is running.",
  },
  {
    name: "maps omg command not found",
    error: "sh: command not found: omg",
    message: "omg command not found.",
    suggestion: "Add omg to PATH or use `npx omg`.",
  },
  {
    name: "maps missing module",
    error: new Error("Cannot find module 'foo'"),
    message: "A dependency could not be resolved.",
    suggestion: "Run `bun install` to restore dependencies.",
  },
  {
    name: "maps timeout",
    error: "ETIMEDOUT: request timed out",
    message: "Operation timed out.",
    suggestion: "Network timeout. Check your connection.",
  },
  {
    name: "maps corrupted config",
    error: new Error("SyntaxError: Unexpected end of JSON input in config file"),
    message: "Configuration file looks corrupted.",
    suggestion: "Run `npx omg env doctor`.",
  },
  {
    name: "maps no space left",
    error: "ENOSPC: no space left on device",
    message: "No space left on device.",
    suggestion: "Disk full. Free up space and try again.",
  },
  {
    name: "maps aborted operation",
    error: new Error("AbortError: The operation was aborted"),
    message: "Operation cancelled.",
    suggestion: "No action needed.",
    exitCode: 130,
  },
  {
    name: "maps generic MCP not found",
    error: "MCP service not found",
    message: "Required MCP integration is missing.",
    suggestion: "Run `npx omg install --apply`.",
  },
];

describe("formatCliError", () => {
  it.each(cases)("$name", ({ error, message, suggestion, exitCode }) => {
    const formatted = formatCliError(error);
    expect(formatted.message).toBe(message);
    expect(formatted.suggestion).toBe(suggestion);
    expect(formatted.exitCode).toBe(exitCode ?? 1);
  });

  it("falls back to unknown error without stack trace", () => {
    const formatted = formatCliError({ foo: "bar" });
    expect(formatted.message).toBe("Unknown error");
    expect(formatted.suggestion).toBe("Check the output above and try again.");
    expect(formatted.exitCode).toBe(1);
  });
});

describe("printCliError", () => {
  it("prints a user-friendly message without stack traces", () => {
    const calls: string[] = [];
    const original = console.error;
    console.error = (...args: unknown[]) => {
      calls.push(args.map(String).join(" "));
    };

    try {
      printCliError(new Error("Cannot find module 'foo'"));
    } finally {
      console.error = original;
    }

    expect(calls.join("\n")).toContain("Error: A dependency could not be resolved.");
    expect(calls.join("\n")).toContain("→ Run `bun install` to restore dependencies.");
    expect(calls.join("\n")).not.toContain("at ");
    expect(calls.join("\n")).not.toContain("Error: Cannot find module");
  });
});
