# Security-Critical Domains

**When:** Touching auth, payment, database, user-data, or privacy-related code.

**Detection signals:** File paths or content containing: auth, login, signup, session, token, password, payment, billing, checkout, stripe, database, migration, schema, user, profile, PII, GDPR, encryption, certificate.

**Required actions:**
1. Before making changes: Read the ENTIRE file, not just the target function. Security bugs hide in adjacent code.
2. Check auth flow end-to-end: login → session creation → token validation → permission check → logout/expiry.
3. Never hardcode: API keys, secrets, tokens, connection strings, passwords. Use env vars or secret manager.
4. Validate all inputs: SQL injection, XSS, command injection, path traversal — check at EVERY entry point.
5. After changes: Request `/OAL:escalate codex "deep security review of [file]: auth flow, injection, privilege escalation"`.
6. Payment code: PCI-DSS awareness — no raw card numbers in logs, no sensitive data in URLs, encrypt at rest.
7. Database code: Parameterized queries ONLY. No string concatenation for SQL. Check migration rollback safety.

**URI hardening checklist (frontend + backend):**
- HTTPS-only enforcement (no mixed content)
- CORS whitelist (not wildcard `*` in production)
- CSP headers configured
- Rate limiting on auth/payment endpoints
- Input sanitization before DB/template rendering
- No sensitive data in URL parameters (use POST body or headers)
- Redirect URLs validated against whitelist (open redirect prevention)

**Evidence:** After touching security-critical code, you MUST run the security check AND note it in your completion message. Saying "looks fine" without verification is unacceptable.
