export interface RetryOptions {
  maxAttempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  jitter?: boolean;
  retryOn?: (error: unknown) => boolean;
}

interface RetryContext {
  readonly attempts: number;
  readonly maxAttempts: number;
  readonly lastDelayMs?: number;
  readonly originalMessage?: string;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message || error.name;
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function toError(error: unknown): Error {
  if (error instanceof Error) return error;
  return new Error(getErrorMessage(error));
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function applyRetryContext(error: unknown, context: RetryContext): Error {
  const err = toError(error);
  const originalMessage = err.message || err.name;
  err.message = `${originalMessage} (retry attempts exhausted after ${context.attempts}/${context.maxAttempts}; last delay ${context.lastDelayMs ?? 0}ms)`;
  (err as Error & { retryContext?: RetryContext }).retryContext = {
    ...context,
    originalMessage,
  };
  return err;
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const maxAttempts = Math.max(1, options.maxAttempts ?? 3);
  const baseDelayMs = Math.max(0, options.baseDelayMs ?? 100);
  const maxDelayMs = Math.max(0, options.maxDelayMs ?? 5000);
  const jitter = options.jitter ?? true;
  const retryOn = options.retryOn ?? (() => true);

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt >= maxAttempts || !retryOn(error)) {
        if (attempt >= maxAttempts) {
          throw applyRetryContext(error, { attempts: attempt, maxAttempts });
        }
        throw error;
      }

      const rawDelay = baseDelayMs * 2 ** (attempt - 1);
      let delay = Math.min(rawDelay, maxDelayMs);
      if (jitter) {
        delay = Math.min(maxDelayMs, delay * (0.5 + Math.random() * 0.5));
      }

      console.warn(
        `Retry attempt ${attempt}/${maxAttempts} failed: ${getErrorMessage(error)}; retrying in ${Math.round(delay)}ms`,
      );
      await sleep(delay);
    }
  }

  throw new Error("unreachable");
}
