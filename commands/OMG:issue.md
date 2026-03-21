---
description: "Unified security diagnostics — parallel sub-agent scanning with ranked issue triage and SARIF output."
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(pytest:*), Bash(rg:*), Bash(grep:*)
argument-hint: "[--agents <csv>] [--format json|text|sarif] [--surfaces <csv>] [--simulate-surface <name> --simulate-scenario <name>]"
---

# /OMG:issue — Unified Security Diagnostics

Parallel sub-agent scanning with ranked issue triage. Subsumes security-check and deps for diagnostics.

## Quick Start

```
/OMG:issue                          # Full scan (all agents)
/OMG:issue --format sarif           # SARIF 2.1 output
/OMG:issue --agents red-team,secret-scan   # Specific agents only
```

## Sub-Agents

| Agent | What It Scans | Categories |
|-------|---------------|------------|
| **red-team** | SSRF, SQLi, XSS, path traversal, command injection | vuln |
| **dep-audit** | Manifest detection, lockfile presence, CVE pointers | cve, license |
| **secret-scan** | API keys, passwords, private keys, cloud credentials | secret |
| **env-scan** | Python version, .env in git, file permissions | env, secret |

All agents run in parallel and their findings are deduplicated, ranked by severity, and assigned trust scores.

## Usage

```bash
# Python API
python3 -c "
from runtime.issue_orchestrator import run_parallel_scan
result = run_parallel_scan('.')
print(f'Findings: {len(result.findings)}')
for f in result.findings[:5]:
    print(f'  [{f.severity}] {f.title} — {f.file_path}:{f.line_number}')
"

# SARIF output for CI integration
python3 -c "
import json
from runtime.issue_orchestrator import run_parallel_scan
result = run_parallel_scan('.')
print(json.dumps(result.to_sarif(), indent=2))
" > .omg/evidence/issues/latest.sarif.json
```

## Output Formats

### Text (default)
```
OMG Issue Scanner — 77 findings
  [critical] Hardcoded API key — config/keys.py:12
  [high] Potential SSRF — services/proxy.py:45
  [medium] No lockfile for package.json
```

### JSON
Full `IssueScanResult` schema with all findings, agent metadata, and summary stats.

### SARIF 2.1
Standard static analysis format for CI/CD integration (GitHub Advanced Security, GitLab SAST, etc).

## Legacy Surfaces

The existing surface-based scan is still available:

```
/OMG:issue --surfaces plugin_interop,governed_tools
/OMG:issue --simulate-surface hooks --simulate-scenario "delete protected lock"
```

Surfaces: `live_session`, `forge_runs`, `hooks`, `skills`, `mcps`, `plugin_interop`, `governed_tools`, `domain_pipelines`

## Finding Schema

```json
{
  "id": "red-team-a1b2c3d4",
  "agent": "red-team",
  "severity": "high",
  "category": "vuln",
  "title": "Potential SSRF: unvalidated URL",
  "description": "Found in services/proxy.py:45: requests.get(url)",
  "file_path": "services/proxy.py",
  "line_number": 45,
  "evidence": "requests.get(url)",
  "remediation": "Validate URL against allowlist",
  "trust_score": 1.0,
  "cve_id": "",
  "cwe_id": ""
}
```

## Evidence

Results are persisted to `.omg/evidence/issues/<run_id>.json` for audit trail.

## Related Commands

- `/OMG:deps` — Deep dependency health (CVE + license + outdated)
- `/OMG:security-check` — Full security pipeline
- `/OMG:validate` — System-level validation
