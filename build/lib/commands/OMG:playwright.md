---
description: "Compatibility alias for /OMG:browser."
allowed-tools: Read, Grep, Glob
argument-hint: "<goal or browser task>"
---

# /OMG:playwright

`/OMG:playwright` is an alias for `/OMG:browser`.

Use the canonical `/OMG:browser` command for public docs, setup guidance, and future OMG browser workflows.

## Compatibility Notes

- This alias exists so Playwright-oriented users can find the browser surface quickly.
- Runtime behavior should resolve to the same OMG browser path as `/OMG:browser`.
- OMG still uses upstream `playwright-cli` under the hood.
