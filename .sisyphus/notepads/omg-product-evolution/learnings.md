# Learnings - omg-product-evolution

## Architecture Conventions
- Python runtime: 150+ modules, CORE (<20) are eagerly loaded, rest lazy
- TypeScript CLI: yargs-based, 651 lines in src/cli/index.ts
- MCP server: stdio-based, 15 existing tools, do NOT change signatures destructively
- Pack schema: REQUIRED=name only, RECOMMENDED=rules/prompts/scaffold/evidence, OPTIONAL=anything else
- Test framework: pytest (Python), bun test (TypeScript)

## Key File Locations
- Pack loader: runtime/pack_loader.py (lazy semantics for 6 packs currently)
- Core boundaries: docs/architecture/core-pack-boundaries.md
- Mutation gate: runtime/mutation_gate.py (8 sequential gates)
- Claim judge: runtime/claim_judge.py
- Worker watchdog: runtime/worker_watchdog.py (60s stall detection)
- Complexity classifier: runtime/complexity_classifier.py (pattern to follow)
- HUD: hud/omg-hud.mjs
- Existing SaaS pack: packs/domains/saas/pack.yaml

## Design Decisions
- Instant mode: single-agent path (not elastic) for predictable first experience
- Pack rules: MAX 5 for new packs (SaaS 9 is grandfathered legacy)
- Silent Safety: NEVER auto-approve rm -rf, DROP TABLE, git push --force, .env/.aws/.ssh writes
- MCP tools: additive OPTIONAL fields only (backward compat), new features = new tools
- HUD: terminal statusline ONLY (no web dashboard)
- Deploy: local preview first, then optional (Vercel > Netlify > CF)
- Loop detection threshold: 3+ identical calls = repetition loop

## Gotchas
- src/mcp/server.ts is TypeScript ESM - use `bunx tsx` NOT `node require()`
- Tests: 5,360+ baseline must be maintained or exceeded
- Schema: saas-lite pack only has name/description/category/dependencies (minimal pack)
- bun test for TypeScript: `bun test tests/hud/test_hud_enhanced.test.ts`
- conftest.py has shared fixtures (tmp_project, mock_stdin, clean_env) - USE THEM

## Pack Schema Validation
- Default pack validation should only require `name`; relaxed mode must allow saas-lite without blocking on missing recommended fields.
- Strict validation should reject missing `rules/prompts/scaffold/evidence`, but still grandfather the 9-rule legacy SaaS pack.
- Unknown extension fields like `instant_mode` must pass through without errors.
