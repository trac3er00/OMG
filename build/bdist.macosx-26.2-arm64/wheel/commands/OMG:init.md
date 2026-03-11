---
description: "Unified initializer — auto-detects: project setup (if no .omg/state), domain scaffolding (if argument given), or health check."
allowed-tools: Read, Write, Edit, MultiEdit, Bash(mkdir:*), Bash(cat:*), Bash(find:*), Bash(ls:*), Bash(head:*), Bash(grep:*), Bash(tree:*), Bash(node:*), Bash(python*:*), Bash(tee:*), Grep, Glob
argument-hint: "[optional: domain name like 'payment', or 'check' for health check]"
---

# /OMG:init — Unified Project & Domain Initializer

## Auto-Detection Logic

```
if argument is a domain name (e.g. "payment", "user-profile"):
  → DOMAIN INIT (create new domain from existing patterns)
elif .omg/state directory does not exist:
  → PROJECT INIT (first-time project setup)
elif .omg/state/profile.yaml exists:
  → HEALTH CHECK (verify everything works, offer upgrades)
```

---

## MODE A: PROJECT INIT (no .omg/state found)

### Step 1: Create .omg/state/profile.yaml (MOST IMPORTANT)
Detect from code. Ask user for anything undetectable.

```yaml
# .omg/state/profile.yaml — injected every session (keep under 20 lines)
name: "[from package.json/Cargo.toml/pyproject.toml]"
description: "[1 sentence]"
repo: "[from git remote -v]"

language: "[detect]"
framework: "[detect]"
database: "[detect or ask]"
infra: "[detect from Dockerfile/terraform/etc]"
key_deps: "[top 5]"

conventions:
  naming: "[detect: camelCase/snake_case]"
  test_cmd: "[detect: npm test/pytest/cargo test]"
  lint_cmd: "[detect: eslint/ruff/clippy]"

ai_behavior:
  communication: "[ask user: language preference]"
  when_stuck: "Ask user after 2 failed attempts"
  testing: "User-journey focused, not boilerplate"
```

### Step 2: Create knowledge structure + OMG v1 contract dirs
```
mkdir -p .omg/state/ledger .omg/knowledge/decisions .omg/knowledge/patterns .omg/knowledge/rules
mkdir -p .omg/trust .omg/evidence .omg/shadow .omg/migrations
```

Copy OMG v1 templates when missing:
- `.omg/idea.yml`
- `.omg/policy.yaml`
- `.omg/runtime.yaml`

### Step 3: Auto-detect quality gate
```json
// .omg/state/quality-gate.json — only include commands that exist
{
  "format": "[detect: prettier/black/gofmt or null]",
  "lint": "[detect: eslint/ruff/clippy or null]",
  "typecheck": "[detect: tsc/mypy or null]",
  "test": "[detect: npm test/pytest/cargo test or null]"
}
```

### Step 4: Copy relevant contextual rules
Based on detected project type, copy relevant rules from templates:
- Web project → security-domains.md, code-hygiene.md
- Backend → infra-safety.md, dependency-safety.md
- DDD project → ddd-sdd.md, outside-in.md

### Step 5: Verify
Run `/OMG:health-check` to confirm setup.

---

## MODE B: DOMAIN INIT (argument = domain name)

### Step 1: Find Reference Pattern
```bash
find . -type f -name "*.ts" -o -name "*.py" | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -10
```
Read the most complete existing domain. Extract:
- Directory structure (routes, services, models, tests)
- Naming conventions, error handling, data flow patterns

### Step 2: Define the New Domain
Ask the user:
- "What entities does [domain] have?"
- "What actions can be performed?"
- "What external services does it talk to?"
- "What are the business rules?"

### Step 3: Generate Domain Structure
Match the reference pattern EXACTLY. Create:
```
src/[domain]/
  ├── [domain].model.ts
  ├── [domain].service.ts
  ├── [domain].repository.ts
  ├── [domain].controller.ts (or routes)
  ├── [domain].types.ts
  └── __tests__/
      └── [domain].service.test.ts
```

### Step 4: Document the Pattern
Save to `.omg/knowledge/patterns/[domain]-pattern.md`

---

## MODE C: HEALTH CHECK (already initialized)

Run `/OMG:health-check` and additionally:
- Verify profile.yaml is up-to-date with current project state
- Check if new contextual rules should be added
- Offer to update quality-gate.json if tools changed

---

## File Write Method
Use `Write` tool first. If it fails (file exists), fall back to:
```bash
cat > .omg/state/profile.yaml << 'EOF'
[content]
EOF
```
Always READ the file after writing to confirm.
