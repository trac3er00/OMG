import { atomicWriteJson, readJsonFile } from "./atomic-io.js";
import { StateResolver } from "./state-resolver.js";

export interface ConversationMessage {
  readonly role: "user" | "assistant" | "system";
  readonly content: string;
}

export type TechnicalLevel = "beginner" | "intermediate" | "advanced";
export type NamingConvention = "camelCase" | "snake_case" | "kebab-case";

export interface UssProfile {
  readonly language: string;
  readonly technicalLevel: TechnicalLevel;
  readonly namingConvention: NamingConvention;
  readonly stack: readonly string[];
}

export interface UssConfig {
  readonly projectDir?: string;
  readonly persistenceKey?: string;
}

type UssPreferenceKey = keyof UssProfile;

const DEFAULT_PROFILE: UssProfile = {
  language: "en",
  technicalLevel: "intermediate",
  namingConvention: "camelCase",
  stack: [],
};

const STACK_KEYWORDS: ReadonlyArray<readonly [string, string]> = [
  ["typescript", "typescript"],
  ["ts", "typescript"],
  ["python", "python"],
  ["py", "python"],
  ["javascript", "javascript"],
  ["js", "javascript"],
  ["bun", "bun"],
  ["node", "node"],
  ["react", "react"],
  ["next", "nextjs"],
];

const BEGINNER_HINTS = [
  /쉽게/g,
  /천천히/g,
  /초보/g,
  /beginner/g,
  /simple/g,
  /explain/g,
];
const ADVANCED_HINTS = [
  /최적화/g,
  /아키텍처/g,
  /성능/g,
  /benchmark/g,
  /optimi[sz]e/g,
  /architecture/g,
];

function cloneProfile(profile: UssProfile): UssProfile {
  return {
    language: profile.language,
    technicalLevel: profile.technicalLevel,
    namingConvention: profile.namingConvention,
    stack: [...profile.stack],
  };
}

function isHangul(text: string): boolean {
  return /[ㄱ-ㅎㅏ-ㅣ가-힣]/.test(text);
}

function normalizeToken(text: string): string {
  return text.toLowerCase();
}

function detectLanguage(
  messages: readonly ConversationMessage[],
): string | null {
  let koreanVotes = 0;
  let englishVotes = 0;

  for (const message of messages) {
    if (isHangul(message.content)) {
      koreanVotes += 1;
      continue;
    }
    if (/[a-z]/i.test(message.content)) {
      englishVotes += 1;
    }
  }

  if (koreanVotes === 0 && englishVotes === 0) {
    return null;
  }

  return koreanVotes >= englishVotes ? "ko" : "en";
}

function detectTechnicalLevel(
  messages: readonly ConversationMessage[],
): TechnicalLevel | null {
  const combined = messages.map((message) => message.content).join("\n");
  if (ADVANCED_HINTS.some((pattern) => pattern.test(combined))) {
    return "advanced";
  }
  if (BEGINNER_HINTS.some((pattern) => pattern.test(combined))) {
    return "beginner";
  }
  return messages.length > 0 ? "intermediate" : null;
}

function detectNamingConvention(
  messages: readonly ConversationMessage[],
): NamingConvention | null {
  let camelVotes = 0;
  let snakeVotes = 0;
  let kebabVotes = 0;

  for (const message of messages) {
    const content = message.content;
    camelVotes += (content.match(/\b[a-z]+(?:[A-Z][a-z0-9]+)+\b/g) ?? [])
      .length;
    snakeVotes += (content.match(/\b[a-z0-9]+(?:_[a-z0-9]+)+\b/g) ?? []).length;
    kebabVotes += (content.match(/\b[a-z0-9]+(?:-[a-z0-9]+)+\b/g) ?? []).length;
  }

  if (camelVotes === 0 && snakeVotes === 0 && kebabVotes === 0) {
    return null;
  }
  if (snakeVotes >= camelVotes && snakeVotes >= kebabVotes) {
    return "snake_case";
  }
  if (kebabVotes >= camelVotes && kebabVotes >= snakeVotes) {
    return "kebab-case";
  }
  return "camelCase";
}

function detectStack(messages: readonly ConversationMessage[]): string[] {
  const combined = normalizeToken(
    messages.map((message) => message.content).join("\n"),
  );
  const detected = new Set<string>();

  for (const [keyword, normalized] of STACK_KEYWORDS) {
    const pattern = new RegExp(`(^|[^a-z])${keyword}([^a-z]|$)`, "i");
    if (pattern.test(combined)) {
      detected.add(normalized);
    }
  }

  return [...detected].sort();
}

function sanitizeProfile(candidate: unknown): UssProfile {
  if (!candidate || typeof candidate !== "object") {
    return cloneProfile(DEFAULT_PROFILE);
  }

  const record = candidate as Partial<Record<UssPreferenceKey, unknown>>;
  const stack = Array.isArray(record.stack)
    ? record.stack.map((entry) => String(entry).toLowerCase())
    : [];
  const technicalLevel =
    record.technicalLevel === "beginner" ||
    record.technicalLevel === "advanced" ||
    record.technicalLevel === "intermediate"
      ? record.technicalLevel
      : DEFAULT_PROFILE.technicalLevel;
  const namingConvention =
    record.namingConvention === "snake_case" ||
    record.namingConvention === "kebab-case" ||
    record.namingConvention === "camelCase"
      ? record.namingConvention
      : DEFAULT_PROFILE.namingConvention;

  return {
    language:
      typeof record.language === "string" && record.language.trim().length > 0
        ? record.language
        : DEFAULT_PROFILE.language,
    technicalLevel,
    namingConvention,
    stack: [...new Set(stack)],
  };
}

export class UserSessionServices {
  private readonly profilePath: string | null;
  private profile: UssProfile;

  constructor(config: UssConfig = {}) {
    this.profilePath = config.projectDir
      ? new StateResolver(config.projectDir).resolve(
          config.persistenceKey ?? "uss-profile.json",
        )
      : null;
    this.profile = this.loadProfile();
  }

  private loadProfile(): UssProfile {
    if (!this.profilePath) {
      return cloneProfile(DEFAULT_PROFILE);
    }

    try {
      return sanitizeProfile(readJsonFile<UssProfile>(this.profilePath));
    } catch {
      return cloneProfile(DEFAULT_PROFILE);
    }
  }

  private persist(): void {
    if (!this.profilePath) {
      return;
    }
    atomicWriteJson(this.profilePath, this.profile);
  }

  getProfile(): UssProfile {
    return cloneProfile(this.profile);
  }

  updateFromConversation(messages: readonly ConversationMessage[]): UssProfile {
    if (messages.length === 0) {
      return this.getProfile();
    }

    const nextProfile: UssProfile = {
      language: detectLanguage(messages) ?? this.profile.language,
      technicalLevel:
        detectTechnicalLevel(messages) ?? this.profile.technicalLevel,
      namingConvention:
        detectNamingConvention(messages) ?? this.profile.namingConvention,
      stack: (() => {
        const detected = detectStack(messages);
        return detected.length > 0 ? detected : [...this.profile.stack];
      })(),
    };

    this.profile = sanitizeProfile(nextProfile);
    this.persist();
    return this.getProfile();
  }

  getPreference<K extends UssPreferenceKey>(key: K): UssProfile[K] {
    return this.profile[key];
  }

  setPreference<K extends UssPreferenceKey>(
    key: K,
    value: UssProfile[K],
  ): UssProfile {
    this.profile = sanitizeProfile({
      ...this.profile,
      [key]: value,
    });
    this.persist();
    return this.getProfile();
  }

  suggestApproach(task: string): string {
    const profile = this.getProfile();
    const preferredStack =
      profile.stack.length > 0
        ? profile.stack.join(", ")
        : "the existing project stack";
    const languageLead =
      profile.language === "ko"
        ? "한국어로 설명하고"
        : "Explain in English and";
    const levelLead =
      profile.technicalLevel === "beginner"
        ? "keep the plan simple"
        : profile.technicalLevel === "advanced"
          ? "optimize for depth and tradeoffs"
          : "balance clarity with implementation detail";

    return `${languageLead} approach ${task} using ${preferredStack}, prefer ${profile.namingConvention} naming, and ${levelLead}.`;
  }
}

export function createUserSessionServices(
  config: UssConfig = {},
): UserSessionServices {
  return new UserSessionServices(config);
}

export { DEFAULT_PROFILE as USS_DEFAULT_PROFILE };
