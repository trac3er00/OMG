# Issues — omg-v3-validated

## Discovered Issues
(will be populated as tasks complete)

- Bun was missing before setup; pre-install test baseline failed with `bun: command not found`.
- `pytest` is not installed in the current environment, so Python test collection could not run.
- `bunx tsc --noEmit` still reports 1 TypeScript error in `src/orchestration/hud.test.ts` about `durabilityMetrics` vs `SessionSnapshot`.
- `lsp_diagnostics` is currently unavailable for JSON files because the configured `biome` LSP is not installed in this environment.
- Task 2 baseline: `bun test` completed with 1495 pass / 0 fail / 0 skip; TypeScript compiler still reports the pre-existing `durabilityMetrics` type mismatch.
- Task 3 baseline: `pytest` command was unavailable and `pip3` was also unavailable, so the Python baseline was recorded with `pytestAvailable=false` and `error=1`.

- 2026-04-10: TS memory-store remains monolithic with no Auto/Micro/Ship tier routing, causing downstream CMMS-related roadmap tasks to present as phantom deliverables.
- 2026-04-10: TS autoresearch CLI exposes on-demand mode only; Python daemon helpers exist but are not surfaced through the CLI.
- 2026-04-10: `runtime/memory_encrypt.py` is missing even though the v3 roadmap explicitly references it as part of the CMMS Python deliverable set.
- 2026-04-10: `SkillLifecycleManager.record_use()` in `runtime/skill_evolution.py` promotes skills after 5 successes but fails to retire them after 3 consecutive failures because the promotion check runs before the retirement check.
- 2026-04-10: `runtime/autoresearch_engine.py` contains local budget/read-only checks, but the audit did not find real `hooks/firewall.py` integration despite the roadmap claim.
- 2026-04-10: `runtime/providers/provider_registry.py` marks `claude` as confirmed without a matching `runtime/providers/claude_provider.py` adapter file.
- 2026-04-10: Task 11 validation confirmed `bun test src/state/` passes, but TypeScript memory still has no Auto/Micro/Ship CMMS tier routing while Python memory does, so dual-runtime memory behavior remains intentionally drifted.
- 2026-04-10: Task 11 validation also confirmed Python memory imports cleanly, but the roadmap-referenced `runtime/memory_encrypt.py` module is still missing from the Python runtime layout.
- Task 10: added MutationGate warn-path coverage for exemption overrides, SecretGuard API_KEY redaction coverage, and explicit crypto round-trip coverage.
- Task 10: TypeScript LSP diagnostics could not run because typescript-language-server is not installed in this environment.
- 2026-04-10 Task 8: `src/mcp/server.ts` was only registering `omg_ping` plus `newCapabilityTools`, so canonical health/policy/verification MCP tools were absent from `tools/list` until the built-in registry was restored.
- 2026-04-10 Task 8: MCP server handlers needed explicit error-result wrapping so malformed tool payloads return structured MCP errors instead of tearing down the request path.

- 2026-04-10 Task 7: orchestration validation added direct coverage for exec-kernel passthrough delegation, session event retention, skeptical routing checks, execution-controller registration, and checkpoint-backed pause/continue state round-trips.
- 2026-04-10 Task 7: TypeScript LSP diagnostics are still unavailable in this environment because typescript-language-server is not installed, so bun test evidence was used to confirm changed orchestration tests compile and pass.
- 2026-04-10 Task 9: `ToolFabric.evaluateRequest()` previously swallowed ledger write failures and `getLedgerEntries()` tolerated malformed JSONL; validation now requires write/read errors to surface so persisted governance decisions are auditable.
- 2026-04-10 Task 9: enforcement validation confirmed `MutationGate` is a hard block for dangerous mutations, while `ToolFabric` remains soft-block overall because the default lane still passes through unless a restrictive lane is explicitly configured.
- 2026-04-10 Task 13: Python hook validation exposed missing import-friendly helper entry points in `hooks/firewall.py` and `hooks/secret-guard.py`; added callable screening helpers plus lifecycle coverage proving the TypeScript hook manager preserves `pre-tool -> tool -> post-tool` ordering.
- 2026-04-10 Task 14: validation strengthened target-module coverage with explicit context freshness scaling assertions, deterministic calibration accuracy/FPR/FNR checks, and a five-perspective debate convergence test that confirms non-blocking consensus emerges with dissent recorded.
- 2026-04-10 Task 14: `bun test src/context/ src/reliability/ src/debate/` passed with 228 pass / 0 fail and evidence logged to `.sisyphus/evidence/task-14-modules.log`.
- 2026-04-10 Task 14: TypeScript `lsp_diagnostics` on changed test files could not run because `typescript-language-server` is not installed in this environment; Bun test + build were used as verification evidence instead.
- 2026-04-10 Task 12: verification validation confirmed `bun test src/verification/` passes at 86 pass / 0 fail after adding stale-artifact blocking coverage to `proof-gate`, plus an explicit proof-gate rejection case for claims without evidence.
- 2026-04-10 Task 12: TypeScript LSP diagnostics remain unavailable in this environment because `typescript-language-server` is not installed, so clean verification was established with Bun test evidence instead.
