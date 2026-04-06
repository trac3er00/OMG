# Security Hardening

## Transport

- All external traffic MUST use HTTPS with TLS 1.2+ and HSTS enabled (`max-age=31536000; includeSubDomains`).
- API responses MUST include security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
- CORS MUST be configured with explicit allowed origins. Never use `*` in production.

## Input Validation

- All user input MUST be validated on the server side regardless of client-side validation.
- SQL injection: use parameterized queries or ORM exclusively. No string concatenation for SQL.
- XSS: sanitize and escape all user-generated content rendered in HTML contexts.
- SSRF: validate and restrict outbound URLs to prevent internal network access via user-supplied URLs.
- File uploads: validate MIME type, enforce size limits, and store outside the web root.

## Secrets Management

- Application secrets MUST NOT be committed to version control.
- Use a secrets manager (Vault, AWS Secrets Manager, GCP Secret Manager) or encrypted environment variables.
- Database credentials, API keys, and encryption keys MUST be rotatable without downtime.
- Secrets MUST NOT appear in logs, error messages, or API responses.

## Dependency Security

- Dependencies MUST be audited regularly (`npm audit`, `pip audit`, Snyk, Dependabot).
- Known-vulnerable dependencies MUST be patched within 7 days for critical CVEs, 30 days for high.
- Lock files (`package-lock.json`, `poetry.lock`) MUST be committed and used in CI.

## Infrastructure

- Containers MUST run as non-root users.
- Database access MUST use least-privilege credentials per service.
- Network segmentation: application servers, databases, and internal services MUST be on separate network segments.
- Admin panels and internal tools MUST NOT be exposed to the public internet without VPN or IP allowlisting.

## Incident Response

- A security incident response plan MUST be documented and rehearsed.
- Tenant notification for data breaches MUST comply with applicable regulations (GDPR 72-hour rule, etc.).
- Post-incident review MUST produce a root cause analysis and remediation items tracked to completion.
