# Audit Logging

## What to Log

Every security-relevant and business-critical action MUST produce an audit log entry:

- Authentication events: login, logout, MFA challenge, failed attempts, session invalidation.
- Authorization events: permission denied, role changes, API key creation/revocation.
- Tenant lifecycle: creation, suspension, deletion, plan changes.
- Billing events: subscription changes, payment success/failure, refunds.
- Data access: bulk exports, admin data views, cross-tenant access (if permitted).
- Configuration changes: feature flag toggles, rate limit overrides, webhook config changes.
- User management: invitations, role assignments, user deactivation.

## Log Schema

Every audit log entry MUST include:

```json
{
  "event_type": "user.role.changed",
  "timestamp": "2025-01-15T10:30:00Z",
  "actor": {
    "type": "user",
    "id": "usr_abc123",
    "ip": "203.0.113.42"
  },
  "tenant_id": "ten_xyz789",
  "resource": {
    "type": "user",
    "id": "usr_def456"
  },
  "changes": {
    "before": { "role": "member" },
    "after": { "role": "admin" }
  },
  "request_id": "req_001",
  "source": "dashboard"
}
```

## Storage and Retention

- Audit logs MUST be append-only. No updates or deletes.
- Audit logs MUST be stored separately from application logs.
- Retention: minimum 1 year for standard tenants, 7 years for regulated industries.
- Audit logs MUST be included in tenant data exports where regulation requires it.

## Access

- Tenants MUST be able to view their own audit logs via dashboard or API.
- Audit log access MUST itself be audit-logged (meta-auditing).
- Admin/super-admin access to tenant audit logs MUST be restricted and logged.

## Integrity

- Audit log entries MUST be tamper-evident (hash chaining or write-once storage).
- Log shipping to an external SIEM or log aggregator is RECOMMENDED for forensic durability.
