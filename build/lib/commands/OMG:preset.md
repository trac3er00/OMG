---
description: "Inspect or apply the canonical OMG preset for the current project."
allowed-tools: Read, Write, Edit, Bash(python*:*), Bash(ls:*), Bash(grep:*)
argument-hint: "[safe|balanced|interop|labs|buffet|plugins-first]"
---

# /OMG:preset

Inspect or apply the canonical OMG preset for the current project.

## Usage

```text
/OMG:preset
/OMG:preset safe
/OMG:preset balanced
/OMG:preset interop
/OMG:preset labs
/OMG:preset buffet
/OMG:preset plugins-first
```

## Presets

- `safe`: minimum managed OMG surface
- `balanced`: safe defaults plus extra productivity MCPs
- `interop`: coexistence and shared-memory oriented setup
- `labs`: enables experimental and browser-heavy surfaces
- `buffet`: full preset; enables every managed preset flag
- `plugins-first`: compatibility alias for `interop`

## Behavior

When a preset is supplied:

1. Resolve the requested preset through `runtime.adoption.resolve_preset`.
2. Persist the canonical preset via `hooks.setup_wizard.set_preferences(...)`.
3. Update project preset metadata in `.omg/state/cli-config.yaml` and project `settings.json` when present.
4. Report the resolved preset, enabled features, and selected MCP defaults.

When no preset is supplied:

1. Read the current project preset from `.omg/state/cli-config.yaml` or project `settings.json`.
2. Report the resolved preset and its managed feature flags.

## Notes

- `buffet` is the top-tier preset and should be treated as a superset of `labs`.
- If the host install also needs updating, rerun `/OMG:setup` with the same preset so the host-level command and MCP surfaces stay aligned.
