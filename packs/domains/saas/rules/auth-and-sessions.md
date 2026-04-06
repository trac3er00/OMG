# Auth and Sessions

## Mandatory

- All API routes MUST check authentication before processing requests.
- Session tokens MUST be short-lived (max 1 hour) with refresh token rotation.
- Password hashing MUST use bcrypt, scrypt, or argon2id — never MD5 or SHA-256 alone.
- OAuth2/OIDC flows MUST validate `state` and `nonce` parameters to prevent CSRF.
- JWT tokens MUST specify `iss`, `aud`, `exp`, and `iat` claims. Never store secrets in JWT payloads.
- API keys MUST be hashed at rest and scoped to the minimum required permissions.

## Session Management

- Server-side session stores (Redis, database) are preferred over stateless JWT for user sessions.
- Session invalidation on password change, role change, or explicit logout is required.
- Concurrent session limits SHOULD be enforced per user or per tenant plan.
- Session fixation: regenerate session ID after successful authentication.

## MFA

- Multi-factor authentication MUST be available for all admin and owner roles.
- TOTP, WebAuthn/passkeys, and recovery codes are acceptable second factors.
- SMS-based MFA is permitted but SHOULD NOT be the only option.

## Service-to-Service Auth

- Internal services MUST authenticate using mTLS or signed JWTs — not shared API keys.
- Service accounts MUST have expiring credentials rotated on a schedule.
