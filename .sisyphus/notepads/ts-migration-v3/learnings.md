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
