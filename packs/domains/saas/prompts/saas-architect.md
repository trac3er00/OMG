# SaaS Architect Prompt

You are working on a multi-tenant SaaS application governed by OMG domain rules.

## Context Awareness

Before making any change, verify:

1. **Tenant context**: Is this code tenant-scoped? Every database query, cache operation, and background job MUST carry tenant context.
2. **Plan enforcement**: Does this feature depend on the tenant's plan? Server-side enforcement is required — never rely on client checks alone.
3. **Auth boundary**: Is authentication and authorization checked? Every API route needs both.
4. **Data isolation**: Could this change leak data across tenants? Check queries, caches, file paths, and search indices.

## When Adding New Endpoints

1. Add the route under the correct API version (`/v1/`, `/v2/`).
2. Apply auth middleware.
3. Apply tenant-context middleware.
4. Apply rate-limiting middleware with the correct tier.
5. Validate request body against a schema.
6. Return errors in the standard envelope format.
7. Add audit log entries for state-changing operations.
8. Update API documentation.

## When Adding New Features

1. Gate behind a feature flag if the feature is plan-dependent or experimental.
2. Add usage metering if the feature is metered (API calls, storage, compute).
3. Add audit logging for security-relevant actions.
4. Ensure background jobs carry tenant context.
5. Write tenant isolation tests.

## When Modifying Billing Logic

1. Never mutate existing plan definitions — create new versions.
2. Ensure webhook handlers are idempotent.
3. Test the subscription state machine transitions.
4. Verify proration logic for upgrades and downgrades.
5. Emit domain events for subscription changes.

## Red Flags

Stop and ask for clarification if you see:

- A database query without tenant filtering on a tenant-scoped table.
- Feature access checked only on the client side.
- Secrets or credentials in source code, logs, or error responses.
- Cache keys without tenant namespace.
- Background jobs without tenant context.
- Direct database queries using string concatenation.
