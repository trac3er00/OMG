# Tenant Onboarding Prompt

Guide for implementing or modifying tenant provisioning flows.

## Onboarding Sequence

A new tenant provisioning MUST follow this order:

1. **Validate input**: Organization name, admin email, selected plan.
2. **Create tenant record**: Assign `tenant_id`, set status to `provisioning`.
3. **Provision resources**:
   - Database schema or row-level config (depending on tenancy model).
   - Storage bucket or prefix.
   - Cache namespace.
   - Search index (if applicable).
4. **Create admin user**: First user with `owner` role, linked to the tenant.
5. **Initialize billing**: Create customer in payment provider, attach plan, start trial if applicable.
6. **Set defaults**: Default feature flags, rate limits, notification preferences.
7. **Send welcome email**: With activation link and getting-started guide.
8. **Update status**: Set tenant status to `active`.
9. **Emit event**: `tenant.provisioned` domain event for downstream consumers.

## Idempotency

- Provisioning MUST be idempotent. If any step fails, retrying the entire flow MUST NOT create duplicates.
- Use a provisioning transaction ID to track and resume partial provisioning.

## Rollback

- If provisioning fails after partial resource creation, clean up created resources.
- Log the failure with full context for debugging.
- Set tenant status to `provisioning_failed` with error details.

## Testing Checklist

- [ ] Successful provisioning creates all resources.
- [ ] Duplicate provisioning request is safely rejected or resumed.
- [ ] Partial failure rolls back cleanly.
- [ ] Admin user can log in after provisioning.
- [ ] Billing is correctly initialized for the selected plan.
- [ ] Tenant data is isolated from other tenants immediately.
