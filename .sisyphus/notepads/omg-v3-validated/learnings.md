## Project Architecture
- Dual-runtime: TypeScript (Bun) + Python (pytest)
- TypeScript: src/ directory, 32+ modules
- Python: runtime/ (200+ files) + control_plane/ + hooks/
- Test runners: bun test (TS), pytest (Python)

## Key Patterns
- Provider adapters: src/providers/{claude,codex,gemini,kimi,opencode}.ts (69-81 line stubs)
- Governance: tool-fabric.ts (PassthroughExecutor default — not hard-blocked)
- Memory: src/state/memory-store.ts (293 lines, monolithic — needs IMSS/DSS/USS refactor)
- AOS harness: src/harness/ (6 files, 844 lines)
- Skills: 27 YAML/markdown descriptors — NO executable code

## Known Issues (from plan research)
- Governance gates default to soft-block, not hard-block
- Integration tests have LSP errors (Bun not installed locally prior to Task 1)
- Only 2 fixture files for 32+ modules
- Provider adapters are stubs (69-81 lines) — need real implementation
- No TypeScript eval infrastructure
- Task 2 baseline: `bun test` passed 1495/1495; `bunx tsc --noEmit` returned 1 existing type error in `src/orchestration/hud.test.ts`.
- Task 3 baseline: Python test collection could not start because `pytest` and `pip3` were unavailable in the environment.

- 2026-04-10: TS audit pattern: passing bun tests were not enough to confirm roadmap completion; multiple modules passed unit tests while still being scaffold-level or disconnected from runtime wiring.
- 2026-04-10: The TS CLI entrypoint is src/cli/index.ts; using src/index.ts only exercises package exports, not CLI behavior.
- 2026-04-10: Python audit pattern: `python3 -m pytest -o addopts=''` is the reliable way to run targeted Python tests here; `pytest` CLI is absent and repo-level addopts trigger xdist/coverage SQLite failures during audit runs.
- 2026-04-10: CMMS Auto/Micro/Ship tiering is genuinely present in `runtime/memory_store.py`/`runtime/memory_schema.py`, but the TypeScript `src/state/memory-store.ts` remains non-tiered, so cross-runtime CMMS claims need explicit drift checks.
- 2026-04-10: `src/state/memory-store.test.ts` already covers the Task 11 minimum contract: encrypted store/read round-trip, PII redaction, and the 10k namespace cap, so this task needed evidence capture and drift documentation instead of new test code.
- 2026-04-10: TypeScript state memory is a narrower contract than Python runtime memory: TS is SQLite-only with namespaced CRUD/search, while Python adds JSON backend support, retention metadata, quarantine/artifact flows, and Ship-tier JSONL persistence.

## [2026-04-10] Wave 1 Audit Findings (Tasks 4-6)

### TypeScript State (Task 4)
- ALL 1495 TS tests pass (0 failures)
- 1 TSC error: src/orchestration/hud.test.ts (durabilityMetrics optional vs required)
- CMMS tiering in TypeScript: NOT IMPLEMENTED (monolithic memory-store.ts)
- AOS harness runner: uses PassthroughExecutor (scaffold only, not real orchestration)
- Governance gates: soft-block (advisory), NOT hard-block (enforced)
- Provider adapters: 69-81 lines, NOT real API implementations
- Targeted test counts: orchestration+governance+security+state=442, mcp=70, verification=84, harness=45, providers=26

### Python State (Task 5)
- pytest NOT installed (pip3 also unavailable)
- Python imports work: runtime OK, control_plane OK
- 146 Python modules in runtime/
- CMMS Auto/Micro/Ship tiering EXISTS in Python (runtime/memory_store.py)
- runtime/memory_encrypt.py is MISSING (referenced in roadmap but doesn't exist)
- skill_evolution.py has lifecycle bug (doesn't retire after 3 failures post-promotion)
- autoresearch_engine.py doesn't integrate hooks/firewall.py
- Python/TS drift highest in: memory, eval

### Fixtures (Task 6)
- 13 fixture files created in tests/fixtures/
- Covers: mcp-request, mcp-response, governance-payload, session-state, memory-entry, provider-response, tool-call, agent-profile
