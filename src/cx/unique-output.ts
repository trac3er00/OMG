import { understandIntent, type IntentAnalysis } from "../intent/index.js";
import type {
  NamingConvention,
  TechnicalLevel,
  UssProfile,
} from "../state/uss.js";

export type CodingStyle = "functional" | "class-based" | "procedural" | string;

export interface UserProfile {
  readonly language: string;
  readonly framework?: string;
  readonly codingStyle?: CodingStyle;
  readonly techLevel?: TechnicalLevel;
  readonly technicalLevel?: TechnicalLevel;
  readonly namingConvention?: NamingConvention;
  readonly stack?: readonly string[];
}

export interface PersonalizedOutput {
  readonly prompt: string;
  readonly profile: {
    readonly language: string;
    readonly framework: string;
    readonly codingStyle: string;
    readonly techLevel: TechnicalLevel;
    readonly namingConvention: NamingConvention;
  };
  readonly intent: IntentAnalysis;
  readonly content: string;
}

interface NormalizedProfile {
  readonly language: string;
  readonly framework: string;
  readonly codingStyle: string;
  readonly techLevel: TechnicalLevel;
  readonly namingConvention: NamingConvention;
}

const KNOWN_FRAMEWORKS = ["react", "vue", "nextjs", "svelte", "angular"];

const TEMPLATE_LIBRARY = {
  en: {
    intro:
      "Build the answer for {framework} with a {codingStyle} style. Task: {prompt}.",
    focus:
      "Primary focus: {domain} work with {effort} effort and {risk} risk. {detailGuide}",
    implementation:
      "Implementation notes: {frameworkGuide} {languageGuide} Keep identifiers in {namingConvention} and pitch the explanation for a {techLevel} developer.",
  },
  ko: {
    intro:
      "{framework} 기준의 {codingStyle} 스타일로 답변을 구성하세요. 작업: {prompt}.",
    focus:
      "핵심 초점: {domain} 작업이며 난이도는 {effort}, 위험도는 {risk}입니다. {detailGuide}",
    implementation:
      "구현 메모: {frameworkGuide} {languageGuide} 식별자는 {namingConvention} 규칙을 유지하고, {techLevel} 수준에 맞춰 설명하세요.",
  },
} as const;

function detectFrameworkFromStack(
  stack: readonly string[] | undefined,
): string | null {
  if (!stack) {
    return null;
  }

  for (const entry of stack) {
    const normalized = entry.trim().toLowerCase();
    if (KNOWN_FRAMEWORKS.includes(normalized)) {
      return normalized;
    }
  }

  return stack[0]?.trim().toLowerCase() ?? null;
}

function normalizeLanguage(language: string): "en" | "ko" {
  return language.trim().toLowerCase().startsWith("ko") ? "ko" : "en";
}

function normalizeProfile(
  profile: UserProfile | UssProfile,
): NormalizedProfile {
  const candidate = profile as UserProfile & Partial<UssProfile>;
  const framework =
    candidate.framework?.trim().toLowerCase() ||
    detectFrameworkFromStack(candidate.stack) ||
    "the existing stack";

  return {
    language: normalizeLanguage(candidate.language),
    framework,
    codingStyle: candidate.codingStyle?.trim().toLowerCase() || "functional",
    techLevel:
      candidate.techLevel ?? candidate.technicalLevel ?? "intermediate",
    namingConvention: candidate.namingConvention ?? "camelCase",
  };
}

function renderTemplate(
  template: string,
  variables: Readonly<Record<string, string>>,
): string {
  return template.replaceAll(/\{(\w+)\}/g, (_, key: string) => {
    return variables[key] ?? "";
  });
}

function describeFramework(
  framework: string,
  codingStyle: string,
  language: string,
): string {
  const isKorean = language === "ko";
  const normalizedFramework = framework.toLowerCase();
  const normalizedStyle = codingStyle.toLowerCase();

  if (normalizedFramework === "react") {
    if (normalizedStyle === "functional") {
      return isKorean
        ? "React 함수형 컴포넌트와 hooks 중심으로 설계하세요."
        : "Use React function components and hooks as the default structure.";
    }
    return isKorean
      ? "React에서 클래식 컴포넌트 패턴과 메서드 구조를 분명히 유지하세요."
      : "Favor React class component patterns with explicit lifecycle-oriented methods.";
  }

  if (normalizedFramework === "vue") {
    if (normalizedStyle === "class-based") {
      return isKorean
        ? "Vue에서는 클래스 기반 컴포넌트처럼 상태와 메서드를 분리해 설명하세요."
        : "Frame the solution with Vue class-style components and clearly separated instance methods.";
    }
    return isKorean
      ? "Vue Composition API와 조합형 패턴을 우선으로 설명하세요."
      : "Prefer Vue Composition API patterns with composables and reactive state.";
  }

  return isKorean
    ? `${framework} 생태계의 관용구와 ${codingStyle} 스타일을 우선하세요.`
    : `Prefer ${framework} conventions and a ${codingStyle} implementation style.`;
}

function describeDetailGuide(
  techLevel: TechnicalLevel,
  language: string,
  intent: IntentAnalysis,
): string {
  const isKorean = language === "ko";

  if (techLevel === "beginner") {
    return isKorean
      ? "단계를 잘게 나누고 전문 용어는 바로 풀이하세요."
      : "Break the solution into small steps and explain jargon immediately.";
  }

  if (techLevel === "advanced") {
    return isKorean
      ? `트레이드오프와 확장성까지 다루고 intent는 ${intent.intent}로 해석하세요.`
      : `Cover tradeoffs and scaling implications, treating this as a ${intent.intent} request.`;
  }

  return isKorean
    ? "구현 디테일과 가독성을 균형 있게 유지하세요."
    : "Balance implementation detail with readability.";
}

function humanizeDomain(domain: string, language: string): string {
  if (language === "ko") {
    const labels: Record<string, string> = {
      frontend: "프론트엔드",
      backend: "백엔드",
      infrastructure: "인프라",
      data: "데이터",
      security: "보안",
      documentation: "문서화",
      other: "일반",
    };
    return labels[domain] ?? domain;
  }

  return domain;
}

function humanizeLevel(level: string, language: string): string {
  if (language === "ko") {
    const labels: Record<string, string> = {
      low: "낮음",
      medium: "중간",
      high: "높음",
      beginner: "입문자",
      intermediate: "중급자",
      advanced: "고급자",
    };
    return labels[level] ?? level;
  }

  return level;
}

function describeLanguageGuide(language: string): string {
  return language === "ko"
    ? "응답은 한국어로 유지하세요."
    : "Respond in English.";
}

export class PersonalizationEngine {
  generate(
    prompt: string,
    profile: UserProfile | UssProfile,
  ): PersonalizedOutput {
    const normalizedProfile = normalizeProfile(profile);
    const intent = understandIntent(prompt);
    const templates =
      normalizedProfile.language === "ko"
        ? TEMPLATE_LIBRARY.ko
        : TEMPLATE_LIBRARY.en;
    const variables = {
      prompt,
      framework: normalizedProfile.framework,
      codingStyle: normalizedProfile.codingStyle,
      domain: humanizeDomain(intent.domain, normalizedProfile.language),
      effort: humanizeLevel(
        intent.complexity.effort,
        normalizedProfile.language,
      ),
      risk: humanizeLevel(
        intent.complexity.riskLevel,
        normalizedProfile.language,
      ),
      detailGuide: describeDetailGuide(
        normalizedProfile.techLevel,
        normalizedProfile.language,
        intent,
      ),
      frameworkGuide: describeFramework(
        normalizedProfile.framework,
        normalizedProfile.codingStyle,
        normalizedProfile.language,
      ),
      languageGuide: describeLanguageGuide(normalizedProfile.language),
      namingConvention: normalizedProfile.namingConvention,
      techLevel: humanizeLevel(
        normalizedProfile.techLevel,
        normalizedProfile.language,
      ),
    } satisfies Record<string, string>;

    return {
      prompt,
      profile: normalizedProfile,
      intent,
      content: [templates.intro, templates.focus, templates.implementation]
        .map((template) => renderTemplate(template, variables))
        .join(" "),
    };
  }
}
