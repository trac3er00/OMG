# Archived Plan

This legacy planning note was superseded by the Bun runtime migration.

Current compatibility implementation lives in:

- `runtime/compat.ts`
- `runtime/team_router.ts`
- `lab/pipeline.ts`
- `scripts/omg.ts`

Use the active Bun verification flow instead of the archived implementation notes:

```bash
bun run typecheck
bun test
bun scripts/check-omg-compat-contract-snapshot.ts --strict-version
```
