---
name: omg-provider-interop
description: Use when Codex needs to choose, combine, or explain OMG interop across Codex, Gemini, and Kimi, including provider bootstrap, host parity, and routing tradeoffs.
metadata:
  short-description: Route across Codex, Gemini, and Kimi
---

# OMG Provider Interop

Use this skill when the task is really about provider choice or provider readiness, not just code changes.

## Core Rules

1. Treat `codex`, `gemini`, and `kimi` as the only supported external provider set.
2. Use `ccg` only for `codex + gemini`.
3. Keep `kimi` scoped to long-context synthesis, workspace inspection, and local runtime analysis.
4. Use `python3 scripts/omg.py providers status`, `bootstrap`, `repair`, and `smoke` to gather evidence before making claims about readiness.
5. If setup is required, prefer `./OMG-setup.sh install` or `update`; Codex skills should be auto-synced unless `--skip-codex-skills` is set.

## When To Read More

- Read [references/provider-routing.md](references/provider-routing.md) when you need the exact OMG routing heuristics and readiness interpretation.

