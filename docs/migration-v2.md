# Migrating To OMG v2 Bun

This repository now ships a Bun + TypeScript runtime as the source of truth.

## What Changed

- `scripts/omg.ts` replaces the old runtime entrypoint
- Claude hooks now execute Bun-backed `.ts` files
- installer preflight requires Bun instead of a separate language runtime
- repo verification uses Bun test, Bun typecheck, and the legacy-runtime cleanliness gate

## Upgrade Flow

1. Install Bun `>= 1.3`
2. Run `./OMG-setup.sh update`
3. Confirm `settings.json` points at `.ts` hook commands
4. Run:

```bash
bun run typecheck
bun test
bun scripts/check-runtime-clean.ts
```

## Runtime Surfaces

- `hooks/*.ts`
- `runtime/*.ts`
- `control_plane/*.ts`
- `lab/*.ts`
- `registry/*.ts`
- `omg_natives/*.ts`
- `tools/*.ts`

## Release Notes

- prerelease tags publish on npm `beta`
- stable tags continue to use `latest`
- `.omg/` artifact locations and the `omg` CLI surface stay stable
