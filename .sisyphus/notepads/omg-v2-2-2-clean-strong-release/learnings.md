## 2026-03-13 T3 canonical hosts
- Prefer `get_canonical_hosts()` for host iteration in policy validation and CLI host choices to prevent roster drift.
- Keep release-readiness host requirements filtered to canonical parity hosts only; do not allow compatibility-only hosts (OpenCode) into release-blocking checks.
- Release-readiness artifact presence checks should derive from canonical host artifact maps instead of hardcoded two-host assumptions.

## 2026-03-13 T5 host-aware compaction thresholds
- Hook-side model detection should follow env precedence (`CLAUDE_MODEL`, `OMG_MODEL_ID`, `OPENAI_MODEL`) before packet fields to preserve host override behavior.
- `runtime.context_limits.compaction_trigger(model_id)` is the safest cross-surface source for compaction defaults; avoid flat pressure thresholds in hooks and HUD.
- HUD compact warnings should be derived from trigger tokens vs runtime context window size, with a pragmatic `200k` fallback when model/host cannot be identified.
