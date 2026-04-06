# Multi-Tenancy

## Isolation Models

Three tenancy models are recognized. Choose one and enforce it consistently:

1. **Database-per-tenant**: Strongest isolation. Each tenant gets a separate database or schema. Required for regulated industries (health, finance).
2. **Schema-per-tenant**: Moderate isolation. Shared database, separate schemas. Good balance of isolation and operational cost.
3. **Row-level isolation**: Shared tables with `tenant_id` column. Lowest operational cost but requires careful query discipline.

## Mandatory Guards

- Every database query in a multi-tenant context MUST include a tenant scope filter. No exceptions.
- ORM default scopes or database-level row-level security (RLS) policies MUST enforce tenant boundaries.
- Cross-tenant data access MUST be impossible from application code without an explicit super-admin bypass that is audit-logged.
- Background jobs and queue consumers MUST carry and enforce tenant context. A job without tenant context MUST fail, not default to a global scope.
- Search indices, caches, and object storage MUST be keyed or partitioned by tenant.

## Tenant Lifecycle

- Tenant provisioning MUST be idempotent and create all required resources (database, storage bucket, config) atomically.
- Tenant suspension MUST revoke all active sessions and API keys immediately.
- Tenant deletion MUST follow a soft-delete → grace period → hard-delete lifecycle with data export available during grace.
- Tenant data export MUST produce a portable format (JSON, CSV) for compliance with data portability regulations.

## Performance Isolation

- Noisy-neighbor protection: per-tenant rate limits, connection pool limits, and compute quotas MUST be configurable.
- Tenant-level metrics (request count, latency, error rate, storage usage) MUST be tracked independently.
