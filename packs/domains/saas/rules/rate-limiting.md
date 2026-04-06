# Rate Limiting

## Strategy

- Rate limiting MUST be applied at the API gateway or reverse proxy layer before requests reach application servers.
- Token bucket or sliding window algorithms are preferred. Fixed window is acceptable for simplicity but has burst edge cases.
- Rate limits MUST be configurable per: tenant, plan tier, endpoint, and HTTP method.

## Tiers

Default rate limit tiers (requests per minute):

| Tier       | Read Endpoints | Write Endpoints | Bulk/Export |
| ---------- | -------------- | --------------- | ----------- |
| Free       | 60             | 20              | 5           |
| Starter    | 300            | 100             | 20          |
| Business   | 1000           | 500             | 50          |
| Enterprise | Custom         | Custom          | Custom      |

- Tenants MUST be able to view their current rate limit allocation and usage via API or dashboard.
- Rate limit overrides for specific tenants MUST be audit-logged.

## Response Headers

Every API response MUST include:

- `X-RateLimit-Limit`: Maximum requests allowed in the window.
- `X-RateLimit-Remaining`: Requests remaining in the current window.
- `X-RateLimit-Reset`: Unix timestamp when the window resets.

When rate limited, return HTTP 429 with:

- `Retry-After`: Seconds until the client should retry.
- Error body explaining which limit was exceeded.

## Abuse Protection

- IP-based rate limiting MUST supplement tenant-based limits to protect against credential-stuffed attacks on auth endpoints.
- Auth endpoints (login, register, password reset) MUST have stricter per-IP limits (e.g., 10/min).
- Repeated 429 responses from the same source SHOULD trigger progressive backoff increases.

## Internal Services

- Service-to-service calls within the platform SHOULD have separate, higher rate limits.
- Circuit breakers MUST be used alongside rate limits to prevent cascade failures.
