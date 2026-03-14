## 2026-03-13 T3 canonical hosts
- Prefer `get_canonical_hosts()` for host iteration in policy validation and CLI host choices to prevent roster drift.
- Keep release-readiness host requirements filtered to canonical parity hosts only; do not allow compatibility-only hosts (OpenCode) into release-blocking checks.
- Release-readiness artifact presence checks should derive from canonical host artifact maps instead of hardcoded two-host assumptions.

## 2026-03-13 T5 host-aware compaction thresholds
- Hook-side model detection should follow env precedence (`CLAUDE_MODEL`, `OMG_MODEL_ID`, `OPENAI_MODEL`) before packet fields to preserve host override behavior.
- `runtime.context_limits.compaction_trigger(model_id)` is the safest cross-surface source for compaction defaults; avoid flat pressure thresholds in hooks and HUD.
- HUD compact warnings should be derived from trigger tokens vs runtime context window size, with a pragmatic `200k` fallback when model/host cannot be identified.

## 2026-03-13 T6 ambiguity lockdown
- Centralize clarification normalization in `runtime/context_engine._extract_clarification(data_or_state)` so context packets, router gates, and firewall policy all consume one schema path.
- Keep ambiguity unresolved semantics tied to `requires_clarification OR missing_slots` so provenance-only packet behavior is preserved even when explicit clarification flag is false.
- Strict ambiguity enforcement should block only mutation-capable and external execution bash modes while leaving local read/search inspection (`ls`, `cat`, `git status`, `rg`) open.
- Expose strict mode via `OMG_STRICT_AMBIGUITY_MODE` (default on) to allow controlled bypass in tests and emergency flows without changing clarification prompt format.

## 2026-03-13 T8 canonical host parity test coverage
- Treat canonical host lists in tests as runtime-derived (`get_canonical_hosts()`) so compiler/parity fixtures do not silently drift when host rosters expand.
- Readiness helpers that emit host-parity evidence must serialize full canonical hosts, not a legacy `claude/codex` subset, or readiness checks produce false missing-output blockers.
- Keep single-host compiler checks parameterized across canonical hosts to prove per-host artifact generation once without duplicating near-identical test fixtures.

## 2026-03-13 T9 evidence profile registry synchronization
- Release-facing evidence profile labels should be derived from `runtime.evidence_requirements.EVIDENCE_REQUIREMENTS_BY_PROFILE` to eliminate parallel hardcoded profile maps.
- `methodology-enforced` and `hash-edit` remain governed tool-fabric surfaces; release-readiness should explicitly reject them when surfaced as evidence profiles.
- Query surfaces should fail explicitly for unknown evidence profiles by emitting machine-readable profile status/error metadata while still preserving fail-closed requirement fallback.

## 2026-03-14 T10 music OMR testbed expansion
- Replace per-fixture if/elif chains with a `_DETERMINISTIC_FIXTURES` dict so adding new score types is a single dict entry, not a code branch.
- General-purpose semitone transposition (`_transpose_note`) is safer than hardcoded note lists; it keeps all key pairs deterministic without per-pair maintenance.
- Evidence schema expansions (trace_metadata, freshness_threshold_secs, fixture_inventory_valid) should be additive fields — bump minor schema version, never remove existing fields that downstream consumers depend on.
- Default fixture inventory should be a module-level constant (`_DEFAULT_FIXTURE_INVENTORY`) so both the testbed and tests can reference the canonical list without drift.
- Workflow daily gate should validate fixture_inventory_valid and run_id linkage explicitly, not just freshness — stale evidence can pass freshness but still have incomplete coverage.
