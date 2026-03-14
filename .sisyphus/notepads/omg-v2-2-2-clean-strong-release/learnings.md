## 2026-03-13 T3 canonical hosts
- Prefer `get_canonical_hosts()` for host iteration in policy validation and CLI host choices to prevent roster drift.
- Keep release-readiness host requirements filtered to canonical parity hosts only; do not allow compatibility-only hosts (OpenCode) into release-blocking checks.
- Release-readiness artifact presence checks should derive from canonical host artifact maps instead of hardcoded two-host assumptions.
