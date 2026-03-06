# OMG v2 Bun Runtime

OMG `v2.0.0` runs on Bun + TypeScript. The public product surface stays stable:

- `omg` remains the CLI entrypoint
- Claude hooks still write to `.omg/`
- standalone install, plugin install, update, and uninstall still go through `OMG-setup.sh`
- team routing, compat, provider status, and release readiness keep the same subcommands

## Requirements

- Bun `>= 1.3`
- Claude Code or a compatible `~/.claude` config
- optional provider CLIs for multi-provider routing: `codex`, `gemini`, `kimi`

## Install

```bash
bun install
./OMG-setup.sh install
```

Plugin bundle mode:

```bash
./OMG-setup.sh install --install-as-plugin
```

Upgrade or remove:

```bash
./OMG-setup.sh update
./OMG-setup.sh uninstall
```

## CLI

Local source execution:

```bash
bun scripts/omg.ts teams --target auto --problem "debug auth regression"
bun scripts/omg.ts ccg --problem "refactor dashboard + API contract"
bun scripts/omg.ts compat list
bun scripts/omg.ts providers status
bun scripts/omg.ts release readiness
```

When installed from npm, the package exposes the same surface as:

```bash
omg teams --target auto --problem "debug auth regression"
```

## Runtime Layout

- `scripts/omg.ts`: Bun CLI
- `hooks/*.ts`: Claude hook entrypoints
- `runtime/*.ts`: routing, compat, provider, and release helpers
- `control_plane/*.ts`: local JSON control-plane API
- `lab/*.ts`: Bun pipeline policy and evaluation flow
- `registry/verify_artifact.ts`: supply-artifact verification
- `omg_natives/index.ts`: Bun-native helper surface
- `tools/*.ts`: Bun support utilities used by commands and tests

Stable `settings.json` only registers hooks that perform work at runtime: session start/end capture, the Bash circuit breaker, tool ledger, post-tool-failure, and stop dispatch.

## Verification

```bash
bun run typecheck
bun test
bun run check:runtime-clean
```

Control plane:

```bash
bun control_plane/server.ts --port 8787
```

## Release Notes

- prerelease tags matching `v*-beta.*` publish to npm with the `beta` dist-tag
- stable tags continue to publish on `latest`
- the repo includes a legacy-runtime cleanliness gate that fails if retired runtime files or stale command references return
