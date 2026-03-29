# Learnings — ts-migration-v3

## Project Conventions
- **Bun ≥1.1.0** required — native TypeScript execution, no tsc build step needed at runtime
- **ESM only** — `"type": "module"` in package.json, no `require()`
- **bun:test** for testing — Jest-compatible API
- **Bun.Database** for SQLite (NOT better-sqlite3 or node:sqlite)
- **node:crypto** for all cryptography (AES-256-GCM, PBKDF2, Ed25519)
- **proper-lockfile** for file locking (no fcntl in Bun)
- **p-queue** for concurrency control (replaces ThreadPoolExecutor)

## Architecture Constraints
- hooks ↔ runtime circular deps resolved via `src/interfaces/` boundary layer
- TypeScript MCP SDK has NO middleware — built manually in Task 3
- napi-rs incompatible with Bun — use pure TypeScript for all native ops
- Bun worker_threads lacks stdin/stdout/stderr and resourceLimits
- All state under `.omg/state/`, encrypted with AES-256-GCM
- Distinguished Engineer quality: zero `as any`, Result types, dependency injection

## Security Constraints
- AES-256-GCM (NOT Fernet/AES-128-CBC, NOT AES-256-CBC)
- PBKDF2-HMAC-SHA256 iterations ≥600,000
- NO XOR fallback encryption
- Hard-blocking gates (not advisory)
- Ed25519 for signing (trust manifests, policy packs)
- JWT for HTTP control plane auth (port 8787, loopback-only default)

## Excluded Scope
- lab/ robotics adapters — EXCLUDED
- python_repl.py, python_sandbox.py — DROPPED
- music_omr_testbed.py — DROPPED

## [2026-03-29] Session started
Wave 1 beginning: Task 1 (project scaffold) runs first, then Tasks 2-6 parallel.
## 2026-03-29T20:46:23Z Task 1: Project Scaffolding Complete
- Bun version: 1.3.11
- tsconfig: strict mode + bundler resolution
- Dependencies installed: typescript, @types/node, eslint, @typescript-eslint/parser, @typescript-eslint/eslint-plugin, prettier, zod, @modelcontextprotocol/sdk, js-yaml, @iarna/toml, p-queue, proper-lockfile, yargs, @types/js-yaml, @types/yargs, @types/proper-lockfile
- Any issues encountered: Bun was not on PATH initially; used /home/claw/.bun/bin/bun. Bun test required a smoke test file because zero-test runs exited nonzero.

## [2026-03-29] Task 4: Bun Spike Complete
- Bun version: 1.3.11
- All 8 assumptions: PASS
- PBKDF2 parity: MATCH
- Key finding: SQLite runtime checks pass when using `bun:sqlite` `Database` constructor fallback (global `Bun.Database` was unavailable in this environment).
- WAL note: In-memory SQLite reports `journal_mode=memory`; file-backed DBs are expected to report `wal`.

## [2026-03-29] Task 3: MCP Middleware Complete
- Test count: 10 tests passing
- Key pattern: Express.js-style stack with typed MiddlewareContext
- Short-circuit: returning {decision:"deny"} from any middleware stops chain

## [2026-03-29] Task 6: Security Validators Complete
- Test count: 34 tests passing
- Added NFC normalization (new vs Python version)
- Path traversal protection: resolve() before comparison
- Key edge cases: empty string, too long, special chars, path traversal

## [2026-03-29] Task 2: Interface Boundary Complete
- Files created: 8 (7 interface files + index.ts)
- Total exported types: 46
- Key insights: Python boundary payloads use snake_case and mixed optional fields; TypeScript boundary contracts normalized these into readonly camelCase interfaces while preserving core semantics (policy decisions, defense state signals, orchestration states, and proof/evidence verdict envelopes).

## [2026-03-29] Task 5: Type Definitions Complete
- Total exported types/schemas: 144
- Python dataclass+TypedDict count: 58
- Zod schemas created: 78
- Key patterns: Python uses TypedDict exclusively (no @dataclass in runtime/hooks domain types), recursive JSON types need interface to break cycle, exactOptionalPropertyTypes works with Zod's .optional() since it produces `T | undefined`
- Re-exported ~25 types from src/interfaces/ to avoid duplication
- Section-separator comments retained for Python source traceability in migration

## [2026-03-29] CRITICAL: SQLite API in this Bun version
- **CONFIRMED**: `Bun.Database` is UNDEFINED in Bun v1.3.11 (this environment)
- **CORRECT**: Use `import { Database } from 'bun:sqlite'`
- All Tasks 8, 12 and any SQLite usage MUST use: `import { Database } from 'bun:sqlite'`
- NOT `new Bun.Database(...)` — this throws TypeError

## [2026-03-29] Wave 1 COMPLETE — 6/61 tasks done
Commits:
- 528f40c0: chore(foundation): initialize TypeScript project with bun
- 6541202b: feat(mcp): middleware wrapper layer for tool hooks
- 7c9f0b98: test(spike): validate 8 Bun runtime assumptions — all pass
- 4a68b886: feat(interfaces): hooks-runtime shared contract boundary
- f9205359: feat(types): port Python dataclasses to TypeScript interfaces + Zod schemas
- 1ecb8796: feat(security): validators + input sanitization with Unicode normalization

All bun:test: 45 pass / 0 fail
All tsc --noEmit: 0 errors
All lsp_diagnostics: 0 errors across 25 files

## [2026-03-29T21:15:11.243028+00:00] Task 7: Crypto Module Complete
- AES-256-GCM roundtrip: verified
- PBKDF2 parity: MATCH with Python
- Ed25519 sign/verify: verified
- Test count: 19 passing
## [2026-03-29T21:18:17+00:00] Task 11: Canonical Taxonomy Complete
- 5 hosts: claude, codex, gemini, kimi, opencode
- OpenCode: compat mode, no hooks/presets
- Test count: 15 passing

## [2026-03-29T21:30:00+00:00] Task 8: State Management Complete
- bun:sqlite Database: works, FTS5 supported
- Atomic I/O: temp+rename pattern implemented
- File locking: proper-lockfile works in bun
- Test count: 18 passing

## [2026-03-29] Task 10: Runtime Contracts Complete
- 9 module paths in defaultLayout: verification_controller, release_run_coordinator, interaction_journal, context_engine, defense_state, session_health, council_verdicts, rollback_manifest, release_run
- Schema versions: context_engine=3, defense_state=2, verification_controller=2, all others=1
- Run ID format: omg-<16-char-hex> (UUID v4 short)
- Python SchemaVersion uses {schema_name, version(semver), required_fields}; TS contracts use simplified ContractSchemaVersion {module, version(int)}
- normalizeRunId: lowercase, strip unsafe, remove .., collapse dashes, 128 char max
- Test count: 17 passing, 100% coverage

## [2026-03-29T21:28:28Z] Task 12: Memory Store Complete
- PII redaction: email, phone, SSN patterns
- Encryption: AES-256-GCM via Task 7 crypto module
- FTS5: virtual table sync on write/delete with namespace filter
- Namespace isolation: verified
- Test count: 16 passing

## [2026-03-29T22:03:37Z] Task 13: Mutation Gate Complete
- Hard-blocking: rm -rf/, curl|bash, critical files all denied
- Exemption system: admin override bypasses critical file protection
- Test count: 26 passing

## [2026-03-29T22:02:10Z] Task 14: Firewall + Policy Engine Complete
- Hard-blocking patterns: destructive, pipe-to-shell, cache-poisoning, secrets
- Test count: 17 passing

## [2026-03-29] Task 15: Secret Guard + Credential Store Complete
- Secret guard blocks: .env, .env.*, credentials.json/yml, .aws/, id_rsa/ed25519, .pem/.key/.p12/.pfx, .netrc, secrets.yml, keystore.*
- Credential store: PBKDF2 600k iterations + AES-256-GCM (replaces Python Fernet)
- Audit log: .omg/state/ledger/secret-access.jsonl
- Store path: .omg/state/ledger/credentials.enc
- deriveKey returns Promise<Buffer> (not Uint8Array) — works with encrypt/decrypt since Buffer extends Uint8Array
- readJsonFile returns T | undefined (not null) — use ?. optional chaining
- Test count: 20 passing (12 secret-guard + 8 credential-store), 100% coverage on both files

## [2026-03-29] Task 16: Defense State Complete
- Risk thresholds: critical=injHits>=3 or cont>=0.7, high=injHits>=1 or cont>=0.4, medium=overthinking>=0.5 or prematureFixer>=0.5
- Trust tiers: local=1.0, balanced=0.7, research/browser=0.0
- Instruction quarantine: 9 patterns (injection, override, jailbreak, role-hijack)
- Test count: 22 passing (8 risk level + 3 manager + 7 quarantine + 4 trust tiers)
- TrustTier type added to src/interfaces/security.ts
- StateResolver.layout().defenseState → .omg/state/defense_state.json

## [2026-03-29T22:03:59Z] Task 17: Injection Defense Complete
- 4 layers: pattern, boundary, entropy, structural
- Key patterns: ignore-prev (0.95), jailbreak (0.92), DAN (0.88)
- BIDI/invisible char sanitization included
- Test count: 12 passing

## [2026-03-29] Task 18: Trust Review Complete
- Ed25519 signing of manifests (upgrade from SHA-256 hashing in Python)
- Scoring: mcp_server_added=50, mcp_server_modified=40, env_permission=60, scope_expanded=70, hook_added=30, hook_modified=20, description_changed=5, unknown=25
- Thresholds: >=80=deny, >=45=ask, <45=allow
- Count multiplier capped at 3
- TrustReviewManager: generate/sign/verify/load manifests via Ed25519 KeyObject
- Manifest path: .omg/trust/manifest.lock.json (StateResolver.resolve("../trust/manifest.lock.json"))
- readJsonFile returns undefined (not null) when file missing
- Test count: 17 passing, 100% line coverage on trust-review.ts
## [2026-03-29] Task 19: Hook System Core Complete
- Reentry guard: Promise-based mutex per hook name (Map<string, Promise<void>>)
- Crash handler: fail-closed for security (→deny), fail-open for others (→allow)
- Performance budget: 100ms for pre-tool hooks
- isBypassMode: checks both `bypass: true` and `permission_mode` field (bypasspermissions/dontask)
- Python _common.py uses file-based locks (fcntl), TS uses in-memory promises (single-process model)
- Pre-existing tsc error in src/interfaces/index.ts (TrustTier re-export) — not from our changes
- Test count: 22 passing, 0 failing
- 8 utilities exported: HookReentryGuard, setupCrashHandler, denyDecision, blockDecision, allowDecision, isBypassMode, bootstrapRuntimePaths, checkPerformanceBudget

## [2026-03-29T18:16:41-04:00] Task 21: Claim Judge Complete
- Zero-evidence claims rejected by default
- 5 evidence profiles: minimal, default, tdd, full, security
- Test count: 9 passing

## [2026-03-29T18:17:29-04:00] Task 20: Proof Gate Complete
- Required primitives: junit, coverage
- Min coverage threshold: 70%
- Test count: 10 passing

## [2026-03-29] Task 23: Artifact Parsers Complete
- JUnit: regex-based XML extraction (no DOM parser needed) — `/<(testsuites?)\b([^>]*)>/i` for root, attr extraction helper
- SARIF: JSON.parse + structural extraction with level-based warning/error counting
- Coverage: object property extraction with snake_case→camelCase mapping
- Browser trace: JSON parse + "trace" or "events" key presence validation (mirrors Python logic)
- Test count: 21 passing, 59 assertions, 100% function coverage
- Result interfaces use union `Summary | Record<string, unknown>` to satisfy both typed access and ArtifactParseResult compatibility
- Pre-existing tsc errors in engine.test.ts and tool-fabric.test.ts are unrelated to this task

## [2026-03-29T22:21:56Z] Task 25: Tool Fabric Complete
- Lane policies: allowedTools, requiresSignedApproval, requiresAttestation
- Ledger: append-only JSONL in .omg/state/ledger/tool-fabric.jsonl
- Test count: 4 passing

## 2026-03-29 Task 22: Test Intent Lock + Compliance Governor Complete
- Lock blocks writes without test evidence when active
- Test file resolution: .ts → .test.ts (preserves extension)
- Evidence matching: exact test file OR stem-based partial match
- Compliance governor: 7 command classes (test, build, vcs, read, write, network, destructive)
- classifyBashCommandMode: 3 modes (read, mutation, external) — ported from Python
- Files already committed in previous batch (32f27836); no separate commit needed
- Test count: 40 passing, 50 expect() calls, 100% line+func coverage on both files

## [2026-03-29] Task 26: Evidence Registry Complete
- Storage: append-only JSONL in .omg/state/ledger/evidence-registry.jsonl
- In-memory cache for fast queries
- EvidenceQuery accepts either projectDir string or EvidenceRegistry instance (avoids stale reads)
- Test count: 17 passing
- Clean LSP diagnostics on all 4 files

## [2026-03-29T22:33:12Z] Task 24: Context Engine Complete
- 8 models in limits.ts (Claude, GPT, Gemini)
- Gemini 1.5 Pro = 1M context
- buildPacket returns all required fields
- Test count: 6 passing

## [2026-03-29] Task 27: MCP Server Core Complete
- Implemented `src/mcp/server.ts` with `McpServer` + `StdioServerTransport` and DI-friendly `createServer()` / `startServer()` factories
- Built-in `omg_ping` tool now returns structured payload `{status:"ok", timestamp:number}` and is listed in `tools/list`
- Middleware wiring path validated: `wrapTool` runs stack `before`/`after` around tool execution; deny decisions return MCP tool error payloads (`isError: true`)
- Initialize handshake verified over stdio with protocol `2025-03-26`, serverInfo name `OMG Control MCP`, version `3.0.0`
- Verification: `bun test src/mcp/` passing, `bunx tsc --noEmit` clean, lsp diagnostics clean on changed TypeScript files

## Task 29: Verification/Evidence Tools Registration

- Tool registration pattern: export function returning `ToolRegistration` object with `name`, `description`, `inputSchema`, `handler`
- `exactOptionalPropertyTypes` in tsconfig means `undefined` can't be assigned to optional props — use spread conditionals: `...(condition ? { key: value } : {})`
- `EvidenceRegistry` constructor needs `projectDir`, creates `.omg/state/ledger/evidence-registry.jsonl` on write
- `TestIntentLock` constructor needs `projectDir`, creates `.omg/state/test-intent-lock.json` on acquire
- `detectInjection()` from injection-defense.ts is a pure function (no DI needed) — simplest tool to wrap
- `judgeClaimBatch()` is also pure — maps claims to verdicts with aggregate result
- Test pattern: each tool test uses unique `/tmp` project dirs to avoid state collision
- `createVerificationTools()` convenience function returns all 4 as an array for `CreateServerOptions.tools`

## Task 31: Control Plane Health + Scoreboard

- `exactOptionalPropertyTypes` in tsconfig means optional props (`foo?`) cannot be assigned `undefined` explicitly — must omit the key entirely or use separate return paths
- `SessionHealthProvider` uses DI pattern: accepts `DefenseStateManager` in constructor, static `create()` for convenience wiring
- `src/mcp/tools/` directory was empty — first tool registrations go here
- Health tool pattern: factory function returns `ToolRegistration`, handler is async, validates args then delegates to domain logic
- Guide assert ported from Python: simplified to negative-marker detection + evidence non-empty check
- `StateResolver.layout().defenseState` resolves to `.omg/state/defense_state.json` — `readJsonFile` returns `undefined` when missing, `DefenseStateManager.load()` falls back to DEFAULT_STATE

## [2026-03-29] Task 30: Hook Lifecycle Manager
- Added `HookLifecycleManager` with phase API: `session-start`, `session-end`, `pre-tool`, `post-tool`, `stop-gate` and a `create()` factory that can seed hook ordering from `settings.hooks` registrations.
- Crash handling is phase-aware by default: fail-closed for security-sensitive phases (`pre-tool`, `stop-gate`), fail-open for session/post-tool phases.
- Reentry protection is phase-scoped via `HookReentryGuard.acquire("hook-lifecycle:<phase>")` so concurrent executions serialize safely.
- Pre-tool behavior is deny-first: first `deny`/`block` result short-circuits and prevents tool execution; otherwise manager returns allow.
- Ordering strategy: explicit `priority` wins; otherwise manager derives order from settings hook name registration, then falls back to stable registration order.

## Task 28: Policy/Governance Tool Registration

- ToolRegistration pattern: factory functions with DI deps → returns `{name, description, inputSchema, handler}`
- `inputSchema` is a plain JSON Schema object (Record<string, unknown>), not zod — server.ts wraps it with `z.object({}).passthrough()`
- PolicyDecision action types ("allow"|"warn"|"deny"|"block"|"ask") need mapping to simpler tool response shapes
- `evaluatePolicy` from policy-engine.ts is the unified entry point for bash + file policy checks
- `checkMutationAllowed` accepts 7 positional args — `projectDir`, `lockId`, `exemption` can be null
- `ToolFabric.evaluateRequest` needs filesystem for ledger — mock in tests via DI interface
- `scoreTrustChange` + `getTrustDecision` are pure functions, no mocking needed
- Trust scoring thresholds: ≥80 deny, ≥45 ask, <45 allow
- 100% function coverage on policy.ts with 17 tests

## [2026-03-29] Task 33: Team Router + Critics + Executor
- Auto-target routing works best when signals are layered in priority order: explicit provider mention > domain signal > cost fallback.
- `exactOptionalPropertyTypes` requires optional result keys to be conditionally spread (omit key when value is `undefined`).
- For deterministic parallel-execution tests, keep worker delays equal and assert elapsed time is below sequential sum to verify Promise.all behavior.
- Team router execution is easiest to test via DI (`dispatchFn`) while preserving a static `create()` factory for default runtime wiring.

## [2026-03-29] Tasks 34+35: Decision Engine + Budget Envelopes Complete
- Decision engine: regex-based complexity scoring with 5 levels (trivial→extreme)
- Domain-agent mapping: keyword→agent with category-based provider selection
- Budget envelopes: multi-dimensional tracking (tokens, cpu_ms, memory_mb, wall_time_ms, network_bytes)
- memory_mb uses peak tracking (max), all other dimensions are additive
- Uncapped dimensions (limit=0 or not set) return Infinity remaining and never breach
- BudgetEnvelope.toSnapshot() bridges to the BudgetEnvelope interface from interfaces/orchestration.ts
- Test count: 47 passing (29 decision + 18 budget), 100% function+line coverage

## [2026-03-29] Task 33: Team Router + Selector + Critics + Executor
- Auto-target routing should prioritize explicit provider mentions, then domain hints (code/infra→codex, research→gemini), then fallback cost ranking.
- With `exactOptionalPropertyTypes`, worker result fields must omit undefined keys via conditional object spreads.
- `Promise.all` is a clean mirror of Python thread-pool fan-out for parallel worker dispatch in router execution.

## [2026-03-29] Tasks 36+37: Exec Kernel + Worker Watchdog + Forge System
- ExecKernel captures `executionResult` per run so each `run(task)` persists both run-scoped namespace state and executor output.
- WorkerWatchdog stall detection now clamps negative thresholds to `0ms` before comparison, keeping heartbeat-based stall checks deterministic.
- ForgeSystem keeps canonical domain routing for specialist selection while supporting alias normalization (`vision-agent` → `vision`).
- Invalid forge domains still throw with a valid-domain list, while successful submissions always produce a queued specialist dispatch.

## [2026-03-29] Task 32: Sub-agent Dispatcher + Agent Manager
- Dispatcher + agent lifecycle ports are already present in `src/orchestration/dispatcher.ts` and `src/orchestration/agent-manager.ts`; rerun validations remained green.
- 100-job cap behavior and lifecycle transitions (PENDING→RUNNING→COMPLETED, cancel→CANCELLED) are covered by dedicated tests.
- Verification rerun: `bun test src/orchestration/dispatcher.test.ts`, `bun test src/orchestration/agent-manager.test.ts`, `bun test src/orchestration/`, and `bunx tsc --noEmit` all passed.
