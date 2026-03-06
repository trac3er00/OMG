# Archived Plan

This production-hardening note described the retired runtime implementation. It is kept only as a short archive marker.

The current release-hardening surface is Bun-first and lives in:

- `runtime/release_readiness.ts`
- `scripts/check-omg-compat-contract-snapshot.ts`
- `scripts/check-omg-standalone-clean.ts`
- `.github/workflows/omg-runtime-readiness.yml`

Use the Bun verification stack for current release work:

```bash
bun run typecheck
bun test
bun scripts/check-runtime-clean.ts
```
