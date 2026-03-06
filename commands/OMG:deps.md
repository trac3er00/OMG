---
description: "Scan project dependencies for CVEs, license issues, and outdated packages."
allowed-tools: Read, Bash(bun:*), Grep
argument-hint: "[cves|licenses|outdated]"
---

# /OMG:deps

Run a dependency-health pass against the manifests that still exist in the Bun-era repo.

## Suggested checks

- `package.json` and `bun.lock`
- `Cargo.toml` in `crates/`
- any additional manifest files still committed in the workspace

## Example flow

```bash
bun scripts/omg.ts providers status
bun run typecheck
bun test
```

When reporting dependency health, include:

- manifest files inspected
- known vulnerable or high-risk packages
- license compatibility concerns
- stale packages worth updating before release
