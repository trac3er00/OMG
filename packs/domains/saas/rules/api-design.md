# API Design

## Versioning

- APIs MUST be versioned. Preferred: URL path versioning (`/v1/`, `/v2/`). Header versioning is acceptable.
- Breaking changes MUST increment the major version. Additive changes are non-breaking.
- Deprecated API versions MUST return `Sunset` and `Deprecation` headers with a removal date.
- At least one prior major version MUST remain active for a documented migration period (minimum 6 months for public APIs).

## Request/Response Contracts

- All endpoints MUST accept and return JSON with `Content-Type: application/json`.
- Request bodies MUST be validated against a schema (JSON Schema, Zod, io-ts) before processing.
- Error responses MUST use a consistent envelope:
  ```json
  {
    "error": {
      "code": "RESOURCE_NOT_FOUND",
      "message": "Human-readable explanation",
      "details": []
    }
  }
  ```
- Pagination MUST use cursor-based pagination for list endpoints. Offset pagination is acceptable for admin/internal APIs only.
- Partial responses (`fields` parameter) SHOULD be supported for bandwidth-sensitive clients.

## Authentication and Authorization

- All endpoints MUST require authentication unless explicitly documented as public.
- Authorization MUST be checked after authentication. Use RBAC or ABAC consistently.
- Scoped API keys MUST restrict access to the minimum required endpoints and HTTP methods.

## Rate Limiting

- All endpoints MUST return `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers.
- Rate limit exceeded responses MUST return HTTP 429 with a `Retry-After` header.
- Rate limits MUST be tiered by plan and configurable per tenant.

## Idempotency

- Mutating endpoints (POST, PUT, PATCH) SHOULD accept an `Idempotency-Key` header.
- Idempotent retries within the key's TTL MUST return the original response without re-executing side effects.

## Webhooks (Outbound)

- Webhook payloads MUST be signed (HMAC-SHA256) so recipients can verify authenticity.
- Webhook delivery MUST retry with exponential backoff on failure (at least 3 attempts).
- A webhook log with delivery status MUST be available to tenants.
