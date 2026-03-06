---
name: omg-deep-execution
description: Use when Codex should drive an OMG implementation pass for backend, debugging, security, or algorithm-heavy work, especially when the task should stay Codex-first but still respect OMG routing evidence.
metadata:
  short-description: Codex-first implementation workflow for OMG
---

# OMG Deep Execution

Use this skill when the task belongs primarily on the Codex path.

## Checklist

1. Inspect local context before editing.
2. Treat `codex` as the primary executor for backend, debugging, and security-oriented implementation.
3. Use `python3 scripts/omg.py teams --target codex --problem "<goal>"` when you need a recorded OMG routing artifact.
4. Keep edits minimal, concrete, and verifiable.
5. Hand off to `omg-review-gate` or `omg-verified-delivery` before claiming completion.

## When To Read More

- Read [references/execution.md](references/execution.md) when you need the Codex-first OMG execution sequence.
