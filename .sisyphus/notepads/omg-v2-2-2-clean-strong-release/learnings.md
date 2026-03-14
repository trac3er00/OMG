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
