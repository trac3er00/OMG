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
