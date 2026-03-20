# Rule 05 — Native Option Selector Protocol

## Always Use AskUserQuestion for Choices

When ANY OMG command, skill, or hook presents options to the user, use the `AskUserQuestion` tool — never plain text lists or "reply with a number."

**Why:**
- Creates native UI options the user clicks (not text they type)
- Structured response preserves context across compaction
- Stop hook won't misinterpret a selection as "task complete"
- AI gets unambiguous selection data, not free-text parsing

## Format

```
AskUserQuestion(
  question: "Clear question ending with ?",
  header: "Short label",    // max 12 chars
  options: [
    { label: "Option A (Recommended)", description: "What this does" },
    { label: "Option B", description: "What this does" },
    ...  // 2-4 options
  ],
  multiSelect: false  // true only when choices aren't mutually exclusive
)
```

## Constraints

- **2-4 options per question** (tool limit). "Other" is auto-added for custom input.
- **1-4 questions per call**. Batch related questions when possible.
- Use `preview` field only for code/layout/visual comparisons.
- Put the recommended option FIRST with "(Recommended)" suffix in the label.

## When to Use

- Command presents choices (mode, preset, target, route, theme)
- Hook suggests escalation options (circuit-breaker)
- Wizard step requires user decision (setup, init)
- Plan review asks for next direction (deep-plan, ccg, crazy)

## When NOT to Use

- Confirming a single yes/no action (just ask in plain text)
- Providing information with no choice needed
- Non-interactive mode (`--bypass`, `--non-interactive`)
- Arguments already supplied on the command line

## Hook Integration

Hooks (Python) cannot call AskUserQuestion directly. Instead, hooks MUST
output a structured instruction block that tells the AI to invoke AskUserQuestion:

```
@@ASK_USER_OPTIONS@@
{"question": "...", "header": "...", "options": [...]}
```

The AI reads this sentinel and calls AskUserQuestion with the embedded payload.
Do NOT present plain-text menus from hooks.

> Enforced: All interactive commands include AskUserQuestion in `allowed-tools`.
