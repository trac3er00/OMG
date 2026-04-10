import { describe, test, expect } from "bun:test";
import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { UserSessionServices, USS_DEFAULT_PROFILE } from "./uss.js";

function tmpProjectDir(): string {
  return join(
    tmpdir(),
    `omg-uss-test-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
}

describe("UserSessionServices", () => {
  test("learns Korean TypeScript preferences from mock conversations", () => {
    const projectDir = tmpProjectDir();
    try {
      const uss = new UserSessionServices({ projectDir });
      const profile = uss.updateFromConversation([
        { role: "user", content: "이거 TypeScript로 해줘" },
        { role: "user", content: "답변은 한국어로 부탁해" },
        {
          role: "user",
          content: "변수명은 userSessionState처럼 camelCase가 좋아",
        },
        { role: "user", content: "TypeScript 조합으로 가자" },
        { role: "user", content: "타입 안정성 중요해" },
      ]);

      expect(profile.language).toBe("ko");
      expect(profile.stack).toEqual(["typescript"]);
      expect(profile.namingConvention).toBe("camelCase");
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  test("learns English Python preferences from mock conversations", () => {
    const projectDir = tmpProjectDir();
    try {
      const uss = new UserSessionServices({ projectDir });
      const profile = uss.updateFromConversation([
        { role: "user", content: "Please implement this in Python." },
        { role: "user", content: "Use snake_case names like user_profile." },
        { role: "user", content: "Keep the explanation in English." },
        {
          role: "user",
          content: "I care about architecture and performance tradeoffs.",
        },
        { role: "user", content: "A small Flask-style API is fine." },
      ]);

      expect(profile.language).toBe("en");
      expect(profile.stack).toContain("python");
      expect(profile.namingConvention).toBe("snake_case");
      expect(profile.technicalLevel).toBe("advanced");
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  test("gracefully returns defaults for a new user", () => {
    const uss = new UserSessionServices();
    expect(uss.getProfile()).toEqual(USS_DEFAULT_PROFILE);
    expect(uss.getPreference("language")).toBe("en");
  });

  test("suggestApproach reflects learned preferences", () => {
    const uss = new UserSessionServices();
    uss.updateFromConversation([
      { role: "user", content: "이거 TypeScript로 해줘" },
      { role: "user", content: "한국어로 설명해줘" },
      { role: "user", content: "이름은 taskRunner처럼 camelCase로" },
      { role: "user", content: "구현 세부사항도 같이 알려줘" },
      { role: "user", content: "Bun 환경으로 작업 중이야" },
    ]);

    const suggestion = uss.suggestApproach("new API");
    expect(suggestion).toContain("한국어");
    expect(suggestion).toContain("typescript");
    expect(suggestion).toContain("camelCase");
  });

  test("persists only derived profile data across instances", () => {
    const projectDir = tmpProjectDir();
    try {
      const first = new UserSessionServices({ projectDir });
      first.updateFromConversation([
        { role: "user", content: "Please build this in Python" },
        { role: "user", content: "snake_case naming please" },
        { role: "user", content: "Explain it in English" },
        { role: "user", content: "Keep it simple" },
        { role: "user", content: "No raw chat logs, just preferences" },
      ]);

      const second = new UserSessionServices({ projectDir });
      expect(second.getProfile()).toMatchObject({
        language: "en",
        namingConvention: "snake_case",
        stack: ["python"],
      });
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });
});
