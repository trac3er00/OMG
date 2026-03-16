---
description: "Ship — Idea to Evidence to PR"
allowed-tools: Read, Grep, Glob
argument-hint: "[goal or optional path to .omg/idea.yml]"
---

# /OMG:ship

`/OMG:ship` is a compatibility path to the canonical `ship` pipeline in the advanced plugin.

Users invoke `/OMG:ship`; the runtime routes to `plugins/advanced/commands/OMG:ship.md` for execution.
For the full behavior specification, see `plugins/advanced/commands/OMG:ship.md`.

## Compatibility Notes

- This alias exists so users can invoke the ship pipeline from the root command surface.
- Runtime behavior resolves to the advanced `ship` command — same idea-to-evidence-to-PR pipeline, same artifacts.
- OMG uses the `ship` pipeline for canonical idea intake, execution, evidence collection, and PR-ready delivery.
