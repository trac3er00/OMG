---
description: Deep security review — scans for vulnerabilities, hardcoded secrets, auth issues, and injection risks. Escalates to Codex for deep line-by-line analysis.
allowed-tools: Read, Bash(grep:*), Bash(find:*), Bash(cat:*), Bash(git:*), Bash(rg:*), Grep, Glob
argument-hint: "[file or directory to review, or 'all' for full scan]"
---

# /OMG:security-review — Vulnerability Scanner + Deep Review

## Step 1: Scope Detection

Determine what to scan:
- If argument is a file: scan that file deeply
- If argument is a directory: scan all source files in it
- If "all" or no argument: scan git-tracked source files

Identify security-critical files automatically:
```bash
# Auth/session
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.go" -o -name "*.rs" \) | xargs grep -li "auth\|login\|session\|token\|password\|jwt\|oauth" 2>/dev/null

# Payment
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.go" \) | xargs grep -li "payment\|billing\|stripe\|checkout\|card\|price" 2>/dev/null

# Database
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.go" \) | xargs grep -li "query\|SELECT\|INSERT\|UPDATE\|DELETE\|migration\|schema" 2>/dev/null
```

## Step 2: Automated Vulnerability Scan

For each security-critical file, check LINE-BY-LINE:

**2a. Hardcoded Secrets**
```bash
grep -rn "AKIA\|sk_live\|sk_test\|ghp_\|github_pat\|xoxb-\|xoxp-\|eyJ.*\.eyJ" [files]
grep -rn "api[_-]key.*=.*['\"][A-Za-z0-9]" [files]
grep -rn "password.*=.*['\"]" [files] | grep -v "test\|mock\|example\|placeholder"
```

**2b. SQL Injection**
```bash
grep -rn "f\".*SELECT\|f\".*INSERT\|f\".*UPDATE\|f\".*DELETE" [files]
grep -rn "\\.format.*SELECT\|%s.*SELECT\|\\+.*SELECT" [files]
grep -rn "query.*\\$\\{" [files]  # template literal SQL
```

**2c. XSS / Injection**
```bash
grep -rn "innerHTML\|dangerouslySetInnerHTML\|v-html\|\\|safe\b" [files]
grep -rn "eval(\|exec(\|subprocess.*shell=True" [files]
grep -rn "document\\.write\|document\\.location" [files]
```

**2d. Auth/Session Issues**
```bash
grep -rn "jwt\\.decode.*verify.*false\|verify.*False" [files]
grep -rn "cors.*\\*\|origin.*\\*" [files]
grep -rn "httpOnly.*false\|secure.*false\|sameSite.*none" [files]
```

**2e. Path Traversal**
```bash
grep -rn "req\\.params\|req\\.query\|req\\.body" [files] | grep -i "path\|file\|dir"
grep -rn "\\.\\./\|\\.\\.\\\\" [files]
```

**2f. Sensitive Data Exposure**
```bash
grep -rn "console\\.log.*password\|console\\.log.*token\|console\\.log.*secret" [files]
grep -rn "log\\.info.*password\|logger.*token\|print.*secret" [files]
```

## Step 3: Codex Deep Review (for high-risk files)

For files with auth, payment, or database logic:

```
/OMG:escalate codex "Security deep review of [file]:
1. Read every line. Flag any: hardcoded secrets, SQL injection, XSS, CSRF, auth bypass, privilege escalation, insecure deserialization, SSRF.
2. Check auth flow completeness: does every protected route validate the token? Are permissions checked?
3. Check payment flow: is card data handled safely? Are amounts validated server-side?
4. Check database queries: all parameterized? Any raw string concatenation?
5. Rate this file: SAFE / NEEDS_FIX / CRITICAL with specific line numbers."
```

## Step 4: Report

```
Security Review — [scope]
━━━━━━━━━━━━━━━━━━━━━━━━━━

Files scanned: [N]
Security-critical files: [N]

CRITICAL [N]:
  [file:line] Hardcoded API key: [type]
  [file:line] SQL injection: unparameterized query

HIGH [N]:
  [file:line] Missing auth check on protected route
  [file:line] CORS wildcard in production config

MEDIUM [N]:
  [file:line] Sensitive data in console.log
  [file:line] httpOnly not set on session cookie

LOW [N]:
  [file:line] Missing rate limiting on login endpoint

Codex Deep Review:
  [file]: [SAFE|NEEDS_FIX|CRITICAL] — [summary]

Fix priority: [ordered list of what to fix first]
```

## Anti-patterns
- Don't just grep and dump raw output — analyze each finding
- Don't skip test files entirely (they can leak real credentials)
- Don't claim "looks secure" without running ALL checks above
- Don't treat this as optional for auth/payment/database changes
