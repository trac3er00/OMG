export interface FormattedError {
  readonly message: string;
  readonly suggestion: string;
  readonly exitCode: number;
}

function getErrorText(error: unknown): string {
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`;
  }

  return typeof error === "string" ? error : JSON.stringify(error);
}

function hasText(text: string, needle: string): boolean {
  return text.toLowerCase().includes(needle.toLowerCase());
}

export function formatCliError(error: unknown): FormattedError {
  const text = getErrorText(error);
  const lower = text.toLowerCase();

  if (hasText(lower, "aborterror")) {
    return { message: "Operation cancelled.", suggestion: "No action needed.", exitCode: 130 };
  }

  if (hasText(lower, "mcp server not found") || hasText(lower, "omg-control")) {
    return {
      message: "Required MCP server is missing.",
      suggestion: "Run `npx omg install --apply`.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "enoent") && text.includes(".omg")) {
    return {
      message: "OMG environment files are missing.",
      suggestion: "Run `npx omg install --apply` to initialize.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "bun: not found") || (hasText(lower, "bun") && hasText(lower, "not found"))) {
    return {
      message: "Bun is not installed.",
      suggestion: "Install Bun: curl -fsSL https://bun.sh/install | bash",
      exitCode: 1,
    };
  }

  if (hasText(lower, "permission denied")) {
    return {
      message: "Permission denied.",
      suggestion: "Check file permissions or run with appropriate user.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "eaddrinuse")) {
    return {
      message: "Port already in use.",
      suggestion: "Check if another omg process is running.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "command not found: omg") || hasText(lower, "omg: command not found")) {
    return {
      message: "omg command not found.",
      suggestion: "Add omg to PATH or use `npx omg`.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "cannot find module")) {
    return {
      message: "A dependency could not be resolved.",
      suggestion: "Run `bun install` to restore dependencies.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "timed out") || hasText(lower, "etimedout")) {
    return {
      message: "Operation timed out.",
      suggestion: "Network timeout. Check your connection.",
      exitCode: 1,
    };
  }

  if ((hasText(lower, "unexpected end of json") || hasText(lower, "syntaxerror")) && hasText(lower, "config")) {
    return {
      message: "Configuration file looks corrupted.",
      suggestion: "Run `npx omg env doctor`.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "enospc")) {
    return {
      message: "No space left on device.",
      suggestion: "Disk full. Free up space and try again.",
      exitCode: 1,
    };
  }

  if (hasText(lower, "mcp") && hasText(lower, "not found")) {
    return {
      message: "Required MCP integration is missing.",
      suggestion: "Run `npx omg install --apply`.",
      exitCode: 1,
    };
  }

  const message = error instanceof Error ? error.message : typeof error === "string" ? error : "Unknown error";
  return {
    message,
    suggestion: "Check the output above and try again.",
    exitCode: 1,
  };
}

export function printCliError(error: unknown): void {
  const { message, suggestion } = formatCliError(error);
  console.error(`\nError: ${message}`);
  if (suggestion) {
    console.error(`  → ${suggestion}`);
  }
  console.error("");
}
