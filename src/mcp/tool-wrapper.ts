import { MiddlewareStack } from "./middleware.js";
import type { ToolHandler } from "./types.js";

export function wrapTool<TArgs extends Record<string, unknown>>(
  toolName: string,
  handler: ToolHandler<TArgs>,
  stack: MiddlewareStack,
  projectDir: string,
  sessionId?: string,
): ToolHandler<TArgs> {
  return async (args: TArgs): Promise<unknown> => {
    const ctx = MiddlewareStack.createContext(
      toolName,
      args as Record<string, unknown>,
      projectDir,
      sessionId,
    );

    return stack.execute(ctx, () => handler(args));
  };
}
