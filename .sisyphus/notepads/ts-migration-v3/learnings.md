# TS Migration V3 Learnings

## Tasks 46, 48, 49, 50 — Tool Modules (Browser, LSP, Search, Config)

### Patterns
- All tool modules follow: interface types → deps injection → class with create() factory → sync/async methods
- Git.ts is the canonical reference — readonly interfaces, no as any, .js imports
- Feature flags via process.env with injected isEnabled dep for testability
- bun:test with describe/test/expect — Jest-compatible API

### Browser Tool
- Consent flow is key: requireConsent(action) must be called before any browser operation
- Guards stack: feature-flag check → consent check → input validation → operation
- Returns BrowserResult<ToolCallSpec> — tool-call specs, not actual browser execution

### LSP Client
- connect() verifies binary existence via which — no actual LSP protocol in adapter layer
- discoverServers() checks for known server binaries on PATH
- All operations return null/empty when disconnected — graceful degradation

### Search
- Provider pattern: SearchProvider interface with name + search() method
- Three built-in providers: SyntheticProvider (mock), BraveProvider, ExaProvider
- WebSearch manages provider registry with default-provider selection

### Config Discovery
- Scans for 8 AI tool config patterns (Claude, Cursor, Windsurf, Gemini, Codex, Cline, Copilot, VSCode)
- mergeConfigs() creates tool-keyed map — later entries overwrite earlier for same tool
- Dependency injection for stat/readdir/access enables full test isolation

### Key Decisions
- No actual Playwright/browser dependency — just spec generation
- No actual LSP protocol — just server discovery and location stubs
- BraveProvider/ExaProvider have real API code but not tested against live APIs
- exactOptionalPropertyTypes: true in tsconfig requires careful undefined vs missing handling

## Task 51: Remaining Hooks Port (2026-03-29)

### Patterns
- DI pattern works well for all hook modules — deps interfaces keep FS/IO testable
- Python's `fcntl` file locking not needed in TS — Bun handles atomic writes differently
- Budget governor is the most complex port — combines 3 Python files (_budget.py, _cost_ledger.py, budget_governor.py)
- `noUnusedParameters` is strict — class fields stored but unused get caught by tsc

### Conventions
- All new hook modules use dependency injection via deps interfaces
- Test mocks use in-memory Map<string, string> for file system simulation
- No `as any` or `@ts-ignore` used anywhere — strict types throughout
- ESM only with `.js` extensions in imports

### Files Created
- src/hooks/budget.ts — BudgetConstants, CostLedger, BudgetGovernor
- src/hooks/analytics.ts — AnalyticsHook with tool stats, hotspots, error trends
- src/hooks/compression.ts — CompressionHook with line-priority scoring
- src/hooks/quality.ts — QualityRunner + TddGate with safe-command whitelist
- src/hooks/routing.ts — KeywordRouter + StopGate with composable checks
- src/hooks/memory.ts — MemoryHook + LearningsAggregator
- src/hooks/hooks.test.ts — 51 tests covering all modules

## Tasks 52-53: CLI Entry + Install Planner (2026-03-29)

### Patterns
- CLI entry now uses `yargs` command modules under `src/cli/commands/` with a single dispatcher in `src/cli/index.ts`.
- `InstallPlanner` follows the project DI style: `create()` factory + injectable `probePath/cwd/homeDir` deps for deterministic tests.
- `SetupOrchestrator` cleanly separates `plan()` (preview only) and `apply()` (actual writes), keeping `--plan` mutation-free.

### Implementation Notes
- `--version` is bound to a constant `3.0.0` in the CLI and verified by `src/cli/index.test.ts`.
- Host detection returns canonical booleans for `{ claude, codex, gemini, kimi }` and does not include optional compat hosts.
- Apply mode writes `omg-control` MCP registration for JSON/TOML host configs with safe directory creation.

### Verification
- `bun test src/cli/` output saved to `.sisyphus/evidence/task-52-cli-version.txt`.
- `bun test src/install/` output saved to `.sisyphus/evidence/task-53-install.txt`.
- `bunx tsc --noEmit` and `bun run build` both pass after the new modules were added.

## Task 57: Contract Compiler + Compat Layer (2026-03-29)

### Patterns
- Split compiler into focused modules: `schema.ts` (shape checks), `validation.ts` (policy-level blockers), `host-emit.ts` (host artifact format), `index.ts` (orchestration).
- Keep host artifact emission pure/in-memory (`emitForHost`) so tests validate formats without filesystem side effects.
- Contract validation maps directly to `OMG_COMPAT_CONTRACT.md` provider requirements: base `compilation_targets` + host-specific capability sets.

### Compat Notes
- `CompatLayer` resolves host compatibility and version compatibility in one surface (`resolveCompat`).
- Legacy ecosystem detection should match Python adoption behavior: detect `.omc`, `.omx`, and Superpowers sentinels under `.claude/` fallback.
- For `exactOptionalPropertyTypes`, class fields should use explicit unions (`StateResolver | undefined`) rather than optional field syntax when assigning maybe-undefined values.

### Verification
- `bun test src/runtime/contract-compiler/` passes and validates Claude `.claude-plugin/mcp.json` and Codex `.agents/skills/omg/` artifact formats.
- `bunx tsc --noEmit` passes after tightening typings in compat/install modules.
- Full task evidence saved at `.sisyphus/evidence/task-57-contract-compiler.txt`.

## Tasks 54, 55, 56 — MCP Config Writers + Plugin System + Registry

### Patterns
- MCP config writers follow host-specific formats: Claude/Gemini/Kimi use JSON with `mcpServers`, Codex uses TOML with `mcp_servers`
- Minimal TOML serializer avoids external dep (no tomlkit needed in TS)
- Plugin loader uses zod schemas to validate plugin.json manifests — catches malformed plugins early
- Registry loader handles three distinct artifact types: skills (JSON), bundles (YAML), policy packs (YAML + signature)
- Policy pack verification checks digest match + trusted signer lookup — file content drift since signing correctly results in `verified: false`

### Conventions
- Section dividers (`// ---`) are the established convention across `types/config.ts` and other modules
- `create()` factory pattern used consistently for DI-friendly instantiation
- `import.meta.dir` used in tests to resolve paths relative to test file location (Bun-specific)
- ESM `.js` extension in imports required by bundler moduleResolution

### Gotchas
- fintech.yaml content has drifted since its signature was created — digest mismatch is expected and correct behavior
- `.sisyphus/` directory is gitignored — evidence files need `git add -f`
- Pre-existing tsc errors in `orchestrator.ts` and `compat.ts` are unrelated to this work
- Core plugin has 22 commands (>= 20 requirement), Advanced has exactly 9
