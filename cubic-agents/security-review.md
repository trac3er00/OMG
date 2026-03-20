# Security Hygiene — Cubic Agent Prompt

## Purpose

Detects security risks including secret exposure, unpinned dependencies, and dangerous code patterns that could compromise the project or its users.

## What This Agent Checks

- Secret exposure (API keys, tokens, credentials in code or configs)
- Unpinned actions (GitHub Actions without SHA pinning)
- Dangerous patterns (eval, shell injection, unsafe deserialization)
- Dependency security (known vulnerable packages)

## Monitored File Patterns

- `hooks/*.py`
- `.github/workflows/*.yml`
- `scripts/*.py`
- `runtime/*.py`
- `*.json` (for embedded secrets)
- `.env*` (should not exist in repo)

## When to Update This File

Update this agent when:
- New dependency type or secret pattern is introduced
- New code directories are added that handle sensitive operations
- Security-relevant file patterns change

After updating this file, sync changes to the Cubic dashboard:
Cubic dashboard -> Settings -> Custom Agents -> Security Hygiene
