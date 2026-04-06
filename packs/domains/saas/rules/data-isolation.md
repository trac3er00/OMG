# Data Isolation

## Storage Boundaries

- Tenant data MUST be logically or physically isolated at every persistence layer: database, cache, object storage, search index, message queue.
- File uploads MUST be stored under tenant-scoped prefixes (`s3://bucket/{tenant_id}/...`) with IAM policies preventing cross-tenant access.
- Backups MUST be restorable per-tenant without affecting other tenants.

## Query Safety

- All ORM models with tenant-scoped data MUST have a default scope or mandatory filter that includes `tenant_id`.
- Raw SQL queries MUST pass through a query analyzer or linting rule that rejects queries missing tenant filters on tenant-scoped tables.
- Database views exposed to reporting or analytics MUST enforce tenant context.

## Cache Isolation

- Cache keys MUST be namespaced by tenant: `{tenant_id}:{resource_type}:{resource_id}`.
- Cache invalidation for one tenant MUST NOT affect other tenants.
- Shared/global caches (e.g., feature flags, plan definitions) MUST be clearly separated from tenant-scoped caches.

## Encryption

- Data at rest MUST be encrypted (AES-256 or equivalent).
- Tenant-specific encryption keys (envelope encryption) are RECOMMENDED for regulated workloads.
- Data in transit MUST use TLS 1.2+ with no fallback to plaintext.

## Data Residency

- Tenants requiring data residency (EU, specific country) MUST have their data stored in the specified region.
- Cross-region replication MUST respect residency constraints.
- Data residency configuration MUST be immutable after tenant provisioning unless explicitly migrated.

## Deletion and Retention

- Tenant data deletion MUST be complete: database records, files, cache entries, search index documents, backups (after retention period).
- A deletion certificate or audit log entry MUST be produced confirming complete removal.
- Regulatory retention requirements MUST override deletion requests where applicable, with clear documentation.
