# Infrastructure Safety

**When:** Working with scripts, Docker, Terraform, K8s, DB migrations, CI/CD.

**Rules:**
- `--dry-run` or `--plan` before any destructive operation
- Never hardcode secrets — use env vars or secret managers
- Bash scripts: `set -euo pipefail` + `trap` for cleanup
- Docker: non-root user + health check + specific base image tags
- Terraform: `plan` before `apply`, state locking enabled
- DB migrations: backward-compatible always (old code must still work with new schema)
- CI/CD: test in staging-like environment before production

**Forbidden:** `rm -rf` without confirmation, `chmod 777`, force-push to main, unencrypted credentials in config.
