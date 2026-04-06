# Billing and Subscriptions

## Plan Architecture

- Every tenant MUST have an active plan (including a free tier if offered).
- Plan definitions MUST be version-controlled and immutable once published. Create new versions instead of mutating existing plans.
- Plan limits (seats, storage, API calls, features) MUST be enforced at the application layer, not just displayed in the UI.
- Grace periods for overages MUST be explicit and documented per plan tier.

## Payment Processing

- Never store raw credit card numbers. Use a PCI-compliant payment processor (Stripe, Braintree, Adyen) and store only tokenized references.
- Webhook handlers for payment events MUST be idempotent. Duplicate webhook deliveries MUST NOT result in double charges or double provisioning.
- Failed payment retries MUST follow a configurable schedule (e.g., 1, 3, 5, 7 days) before account suspension.
- Invoice generation MUST include tax calculation appropriate for the tenant's jurisdiction.

## Usage-Based Billing

- Metered usage MUST be recorded in an append-only ledger that is tamper-evident.
- Usage aggregation windows and billing cycles MUST be clearly documented.
- Usage data MUST be available to tenants in near-real-time via API or dashboard.
- Disputes MUST have a resolution workflow that can credit or adjust usage retroactively.

## Subscription State Machine

Valid states and transitions:

```
trial → active → past_due → suspended → cancelled
trial → cancelled
active → cancelled
```

- State transitions MUST emit domain events consumable by other services.
- Downgrade MUST NOT silently delete data that exceeds the new plan's limits. Warn and enforce gracefully.
- Upgrade MUST take effect immediately with prorated billing for the current cycle.

## Compliance

- Refund policies MUST be documented and programmatically enforced.
- Revenue recognition events MUST be emitted for finance system integration.
