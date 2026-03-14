---
description: "Canonical OMG browser automation and verification surface powered by upstream playwright-cli."
allowed-tools: Read, Write, Edit, Bash(python3:*), Bash(node:*), Bash(npx:*), Bash(playwright:*), Bash(which:*), Bash(ls:*), Bash(cat:*), Grep, Glob
argument-hint: "<goal or browser task>"
---

# /OMG:browser

Use this as the canonical OMG browser surface for automation, visual verification, and trace-backed browser evidence.

## Contract

- `/OMG:browser` is the public OMG command.
- Execution is powered by upstream `playwright-cli`.
- OMG owns the command contract, remediation messages, and `.omg/evidence/` artifact normalization.
- This is not a new OMG MCP server.

## Typical Flow

1. Verify `playwright-cli` is installed.
2. Verify browser assets are available.
3. Run the requested browser workflow.
4. Emit normalized screenshots, traces, and browser evidence under `.omg/evidence/`.

## Notes

- Claude users invoke this command directly.
- Codex, Gemini, and Kimi consume the same capability through OMG-managed setup, runtime, and proof flows.
- Use `/OMG:playwright` only as a compatibility alias when needed.
