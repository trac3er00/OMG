import { HostTypeSchema, type HostType } from "../types/config.js";

export interface ProviderUsage {
  readonly inputTokens: number;
  readonly outputTokens: number;
}

export interface ProviderResponse {
  readonly content: string;
  readonly model: string;
  readonly usage: ProviderUsage;
  readonly provider: HostType;
}

export interface StreamEventUsage {
  readonly inputTokens: number;
  readonly outputTokens: number;
}

export type ProviderStreamEventType = "start" | "content" | "done";

export interface ProviderStreamEvent {
  readonly provider: HostType;
  readonly model: string;
  readonly type: ProviderStreamEventType;
  readonly content?: string;
  readonly usage?: StreamEventUsage;
}

export interface ParityVariance {
  readonly field:
    | "content"
    | "model"
    | "usage.inputTokens"
    | "usage.outputTokens";
  readonly baseline: string | number;
  readonly mismatches: ReadonlyArray<{
    readonly provider: HostType;
    readonly value: string | number;
  }>;
}

export interface ParityReport {
  readonly totalResponses: number;
  readonly providersSeen: HostType[];
  readonly missingProviders: HostType[];
  readonly duplicateProviders: HostType[];
  readonly isFormatConsistent: boolean;
  readonly formatInconsistencies: string[];
  readonly variance: ParityVariance[];
}

export interface StreamParityReport {
  readonly isConsistent: boolean;
  readonly formatInconsistencies: string[];
  readonly sequenceByProvider: Partial<
    Record<HostType, ProviderStreamEventType[]>
  >;
}

const EXPECTED_PROVIDERS = HostTypeSchema.options;

export function checkParity(responses: ProviderResponse[]): ParityReport {
  const formatInconsistencies: string[] = [];
  const providersSeen = new Set<HostType>();
  const duplicateProviders = new Set<HostType>();

  for (const [index, response] of responses.entries()) {
    validateResponse(response, index, formatInconsistencies);

    if (providersSeen.has(response.provider)) {
      duplicateProviders.add(response.provider);
    }
    providersSeen.add(response.provider);
  }

  const providers = [...providersSeen];
  const missingProviders = EXPECTED_PROVIDERS.filter(
    (provider) => !providersSeen.has(provider),
  );

  if (missingProviders.length > 0) {
    formatInconsistencies.push(
      `Missing providers: ${missingProviders.join(", ")}`,
    );
  }

  if (duplicateProviders.size > 0) {
    formatInconsistencies.push(
      `Duplicate providers: ${[...duplicateProviders].join(", ")}`,
    );
  }

  return {
    totalResponses: responses.length,
    providersSeen: providers,
    missingProviders,
    duplicateProviders: [...duplicateProviders],
    isFormatConsistent: formatInconsistencies.length === 0,
    formatInconsistencies,
    variance: collectVariance(responses),
  };
}

export function checkStreamParity(
  events: ProviderStreamEvent[],
): StreamParityReport {
  const formatInconsistencies: string[] = [];
  const sequenceByProvider: Partial<
    Record<HostType, ProviderStreamEventType[]>
  > = {};

  for (const [index, event] of events.entries()) {
    validateStreamEvent(event, index, formatInconsistencies);
    const sequence = sequenceByProvider[event.provider] ?? [];
    sequence.push(event.type);
    sequenceByProvider[event.provider] = sequence;
  }

  const baselineProvider = EXPECTED_PROVIDERS.find(
    (provider) => sequenceByProvider[provider] !== undefined,
  );

  if (baselineProvider) {
    const baselineSequence = sequenceByProvider[baselineProvider] ?? [];
    for (const provider of EXPECTED_PROVIDERS) {
      const providerSequence = sequenceByProvider[provider];
      if (!providerSequence) {
        continue;
      }

      if (providerSequence.join(",") !== baselineSequence.join(",")) {
        formatInconsistencies.push(
          `Stream sequence mismatch for ${provider}: expected ${baselineSequence.join(" -> ")}, received ${providerSequence.join(" -> ")}`,
        );
      }
    }
  }

  return {
    isConsistent: formatInconsistencies.length === 0,
    formatInconsistencies,
    sequenceByProvider,
  };
}

function validateResponse(
  response: ProviderResponse,
  index: number,
  issues: string[],
): void {
  if (typeof response.content !== "string") {
    issues.push(`Response ${index} has non-string content`);
  }
  if (typeof response.model !== "string") {
    issues.push(`Response ${index} has non-string model`);
  }
  if (!HostTypeSchema.safeParse(response.provider).success) {
    issues.push(`Response ${index} has invalid provider`);
  }
  if (
    typeof response.usage?.inputTokens !== "number" ||
    !Number.isFinite(response.usage.inputTokens)
  ) {
    issues.push(`Response ${index} has invalid usage.inputTokens`);
  }
  if (
    typeof response.usage?.outputTokens !== "number" ||
    !Number.isFinite(response.usage.outputTokens)
  ) {
    issues.push(`Response ${index} has invalid usage.outputTokens`);
  }
}

function collectVariance(responses: ProviderResponse[]): ParityVariance[] {
  if (responses.length === 0) {
    return [];
  }

  const baseline = responses[0];
  const fields: Array<ParityVariance["field"]> = [
    "content",
    "model",
    "usage.inputTokens",
    "usage.outputTokens",
  ];

  return fields.flatMap((field) => {
    const baselineValue = readField(baseline, field);
    const mismatches = responses
      .slice(1)
      .filter((response) => readField(response, field) !== baselineValue)
      .map((response) => ({
        provider: response.provider,
        value: readField(response, field),
      }));

    if (mismatches.length === 0) {
      return [];
    }

    return [
      {
        field,
        baseline: baselineValue,
        mismatches,
      },
    ];
  });
}

function readField(
  response: ProviderResponse,
  field: ParityVariance["field"],
): string | number {
  switch (field) {
    case "content":
      return response.content;
    case "model":
      return response.model;
    case "usage.inputTokens":
      return response.usage.inputTokens;
    case "usage.outputTokens":
      return response.usage.outputTokens;
  }
}

function validateStreamEvent(
  event: ProviderStreamEvent,
  index: number,
  issues: string[],
): void {
  if (!HostTypeSchema.safeParse(event.provider).success) {
    issues.push(`Stream event ${index} has invalid provider`);
  }
  if (typeof event.model !== "string") {
    issues.push(`Stream event ${index} has non-string model`);
  }
  if (!["start", "content", "done"].includes(event.type)) {
    issues.push(`Stream event ${index} has invalid type`);
  }
  if (event.type === "content" && typeof event.content !== "string") {
    issues.push(`Stream event ${index} is missing content delta`);
  }
  if (
    event.type === "done" &&
    (typeof event.usage?.inputTokens !== "number" ||
      typeof event.usage.outputTokens !== "number")
  ) {
    issues.push(`Stream event ${index} is missing usage totals`);
  }
}
