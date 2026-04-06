# SaaS Incident Response Prompt

Guide for investigating and resolving production incidents in a SaaS context.

## Triage Checklist

When an incident is reported:

1. **Scope**: Is this tenant-specific or platform-wide?
   - Check if the issue reproduces for multiple tenants.
   - Check tenant-specific resource health (database, cache, storage).
2. **Severity**:
   - **P0 (Critical)**: Data loss, security breach, or complete platform outage. All hands.
   - **P1 (High)**: Major feature broken for multiple tenants. Immediate response.
   - **P2 (Medium)**: Degraded performance or feature broken for single tenant.
   - **P3 (Low)**: Minor issue with workaround available.
3. **Isolation**: Can the impact be contained?
   - Toggle feature flags to disable the broken feature.
   - Apply tenant-specific rate limits if one tenant is causing cascade.
   - Enable maintenance mode for affected subsystem.

## Investigation Order

1. Check recent deployments (last 24 hours).
2. Check error rates and latency metrics per tenant.
3. Check audit logs for recent configuration changes.
4. Check infrastructure health (database connections, Redis, queues).
5. Check for noisy-neighbor effects (one tenant overwhelming shared resources).

## Tenant Communication

- Affected tenants MUST be notified if the incident impacts their data or availability.
- Use the status page for platform-wide issues.
- Use direct notification (email, in-app) for tenant-specific issues.
- Provide estimated time to resolution when possible.

## Post-Incident

- Produce a root cause analysis within 48 hours for P0/P1.
- Create remediation items tracked to completion.
- Update runbooks with the new failure mode.
- Review whether monitoring or alerting gaps allowed the issue to persist.
