---
description: "Run an adversarial security review against the project scope — pattern-based static analysis for injections, hardcoded secrets, auth bypasses, and more."
allowed-tools: Read, Bash(python3:*), Bash(python:*), Bash(cat:*), Bash(ls:*)
argument-hint: "[scope] [--severity-floor medium|high|critical] [--output <path>]"
---

# /OMG:red-team — Adversarial Security Review

## Purpose

Runs a static-analysis adversarial scan over the target scope (file or
directory). The scanner checks Python, TypeScript, and JavaScript sources for
common vulnerability patterns including SQL injection, shell injection, XSS,
hardcoded secrets, auth bypasses, and denial-of-service risks.

## Usage

```
npx omg red-team                                  # scan cwd, severity >= medium
npx omg red-team src/                             # scan specific directory
npx omg red-team --severity-floor high            # only high + critical
npx omg red-team --severity-floor critical        # critical only
npx omg red-team --output report.json             # save JSON report to file
npx omg red-team src/ --severity-floor high --output /tmp/report.json
```

## How It Works

1. Delegates to `runtime/adversarial_review.py:AdversarialReview.scan()`.
2. Scans `.py`, `.ts`, `.js`, `.jsx`, `.tsx` files (excludes `node_modules`,
   `__pycache__`, `.git`).
3. Matches lines against categorized regex patterns with severity levels.
4. Filters findings below the severity floor.
5. Returns a structured report with findings, summary counts, and scan metadata.

## Output Format

```
🔴 Red Team Security Report
Scope: . | Severity floor: medium
Findings: 3 total (critical: 1, high: 1, medium: 1)

Top findings:
  [critical] injection: SQL injection via f-string
    File: src/db.py:42
    Fix: Use parameterized queries
  [high] hardcoded_secret: Hardcoded credential detected
    File: config.py:10
    Fix: Use environment variables or secrets manager
```

When `--output` is provided, the full JSON report is written to the specified
path for integration with CI pipelines or other tooling.

## Options

| Flag               | Default  | Description                                           |
| ------------------ | -------- | ----------------------------------------------------- |
| `[scope]`          | `.`      | File or directory to scan                             |
| `--severity-floor` | `medium` | Minimum severity: `low`, `medium`, `high`, `critical` |
| `--output`         | —        | Write full JSON report to this path                   |

## Severity Levels

| Level      | Examples                                |
| ---------- | --------------------------------------- |
| `critical` | SQL injection, code injection via eval  |
| `high`     | Shell injection, hardcoded secrets      |
| `medium`   | XSS risks, sensitive data in logs       |
| `low`      | Unbounded loops, informational patterns |

## Categories

- `injection` — SQL, shell, code, and XSS injection vectors
- `auth_bypass` — Authentication bypass conditions
- `data_leak` — Sensitive data exposure in logs or stdout
- `privilege_escalation` — Privilege escalation patterns
- `denial_of_service` — Unbounded loops and resource exhaustion
- `insecure_dependency` — Known-vulnerable dependency usage
- `hardcoded_secret` — Credentials and API keys in source

## Notes

- Does **not** modify any source files. Read-only analysis.
- Falls back gracefully if the Python runtime is unavailable.
- Designed for pre-commit and CI integration via `--output`.
