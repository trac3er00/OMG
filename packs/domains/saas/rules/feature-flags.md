# Feature Flags

## Architecture

- Feature flags MUST be evaluated at runtime, not at build time.
- Flag evaluation MUST be fast (< 5ms) and cacheable. Use a local cache with background refresh.
- Flag definitions MUST be stored in a central config (database, feature flag service, or config file) — not scattered across code.

## Flag Types

1. **Release flags**: Temporary. Gate incomplete features behind a flag until ready. Remove after full rollout.
2. **Ops flags**: Semi-permanent. Enable/disable operational behaviors (maintenance mode, circuit breakers).
3. **Experiment flags**: Temporary. A/B testing and gradual rollouts. Require metrics integration.
4. **Permission flags**: Permanent. Gate features by plan tier or tenant entitlement.

## Tenant and Plan Scoping

- Permission flags MUST be tied to the tenant's plan or explicit entitlements, not hard-coded.
- Flag evaluation context MUST include: `tenant_id`, `user_id`, `plan_tier`, `environment`.
- Plan-gated features MUST enforce limits server-side. Client-side flag checks are for UX only, not security.

## Lifecycle

- Every flag MUST have an owner and a scheduled review date.
- Release flags MUST be removed within 30 days of full rollout. Stale flags are technical debt.
- Flag removal MUST be a tracked task, not an afterthought.

## Safety

- Flag changes in production MUST be audit-logged with who, when, and what changed.
- Critical ops flags (maintenance mode, kill switches) MUST require elevated permissions to toggle.
- Flag defaults MUST be safe: if the flag service is unreachable, the default value MUST not break the application or expose unreleased features.
