#!/usr/bin/env bun
import { BUDGET_PROMPT_TOTAL } from "./_budget.ts";
import { readJsonFromStdin } from "./_common.ts";

const ZERO_SIGNALS = /^(hello|hi|ok|thanks|yes|no|goodbye|hey there)$/i;
const KEYWORDS =
  /\b(fix|bug|implement|review|refactor|auth|login|jwt|oauth|database|deploy|rewrite|redesign|frontend|backend|ui|ux|css|layout)\b|전체|수정|구현|버그|에러|리팩토링/i;

function buildInjection(prompt: string): string {
  const base = [
    "OMG Bun runtime context:",
    "- Preserve proof-oriented workflow.",
    "- Prefer focused edits and explicit verification.",
    `- Active prompt: ${prompt}`
  ].join("\n");
  return base.length > BUDGET_PROMPT_TOTAL ? base.slice(0, BUDGET_PROMPT_TOTAL) : base;
}

async function main() {
  const payload = await readJsonFromStdin<any>({});
  const prompt = String(payload.user_message || "").trim();
  if (!prompt || ZERO_SIGNALS.test(prompt)) {
    return;
  }
  if (!KEYWORDS.test(prompt)) {
    return;
  }
  process.stdout.write(
    `${JSON.stringify(
      {
        contextInjection: buildInjection(prompt),
        sources: ["omg-bun-runtime"]
      },
      null,
      2
    )}\n`
  );
}

if (import.meta.main) {
  try {
    await main();
  } catch {
    process.exit(0);
  }
}
