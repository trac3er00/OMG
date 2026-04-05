---
name: omg-security-check
description: "Security audit lane that normalizes waivers, fails on unresolved high-risk findings, and requires remediation plus refreshed SARIF/SBOM evidence."
---

# OMG Security Check

Run `runtime/security_check.py:run_security_check` with scope and waiver inputs. If unresolved high-risk findings remain after waiver normalization, fail the task; require remediation notes and regenerate SARIF/SBOM artifacts before continuation.

- Channel: `enterprise`
- Execution modes: `embedded, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/security-check-*.json`
