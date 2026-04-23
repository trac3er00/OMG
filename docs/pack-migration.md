# Pack Migration Plan

## Current State

### Directory Structure

```
packs/
├── goals/          # Simple scaffold packs with run/verify commands
│   ├── api-server/
│   ├── cli-tool/
│   ├── discord-bot/
│   ├── internal-tool/
│   ├── landing/
│   ├── saas/
│   └── schema.yaml
│
└── domains/        # Complex packs with rules, prompts, evidence
    ├── admin/
    ├── api/
    ├── ecommerce/
    ├── landing/
    ├── saas/
    └── saas-lite/
```

### Pack Characteristics

**Goal Packs** (simple, minimal):
- Fields: `name`, `description`, `language`, `framework`, `files`, `run_command`, `verify_command`
- Optional: `env_vars`, `dependencies`, `readme_template`
- Pattern: scaffold + run/verify commands for instant execution

**Domain Packs** (complex, governance-heavy):
- Fields: `name`, `description`, `category`, `extends`, `rules`, `prompts`, `scaffold`, `evidence`, `instant_mode`
- Rich governance with rules, evidence requirements, instant mode config
- Pattern: structured prompts + rules for AI-driven execution

### Overlap

| Pack Name | In goals/ | In domains/ |
|-----------|-----------|-------------|
| landing   | ✓         | ✓           |
| saas      | ✓         | ✓           |

Both directories contain `landing` and `saas` packs with different schemas.

---

## Target State

### Unified Structure

```
packs/
├── schema.yaml          # Unified schema (NEW)
├── goals/               # Preserved until migration complete
│   ├── api-server/
│   ├── cli-tool/
│   ├── discord-bot/
│   ├── internal-tool/
│   ├── landing/
│   └── saas/
└── domains/            # Preserved until migration complete
    ├── admin/
    ├── api/
    ├── ecommerce/
    ├── landing/
    ├── saas/
    └── saas-lite/
```

**Future State** (post-migration):
```
packs/
├── schema.yaml
├── packs.yaml          # Registry of all packs
├── api-server/         # Flattened structure
├── cli-tool/
├── discord-bot/
├── internal-tool/
├── landing/
├── saas/
├── saas-lite/
├── admin/
├── api/
└── ecommerce/
```

---

## Migration Steps

### Phase 1: Schema Definition (COMPLETED ✓)
- [x] Analyze existing pack structures
- [x] Create `packs/schema.yaml` with unified schema
- [x] Document overlap resolution

### Phase 2: Validation (COMPLETED ✓)
- [x] Create `scripts/validate-packs.ts`
- [x] Verify all existing packs pass validation

### Phase 3: Content Migration (TODO)
- [ ] Audit `landing` packs from both directories
  - [ ] `packs/goals/landing/` - simple HTML landing
  - [ ] `packs/domains/landing/` - full Next.js with rules
  - [ ] Decide: merge or keep separate with type distinction

- [ ] Audit `saas` packs from both directories
  - [ ] `packs/goals/saas/` - Express TypeScript starter
  - [ ] `packs/domains/saas/` - Full SaaS with multi-tenancy, billing
  - [ ] Decide: merge or keep separate with type distinction

### Phase 4: Flatten Structure (TODO)
- [ ] Move all packs to top-level `packs/` directory
- [ ] Add `type: goal | domain` field to each pack.yaml
- [ ] Update schema.yaml to reflect flattened structure
- [ ] Update references throughout codebase

### Phase 5: Cleanup (TODO)
- [ ] Remove old `packs/goals/` and `packs/domains/` directories
- [ ] Update documentation
- [ ] Run final validation

---

## Overlap Resolution

### Strategy: Type-Based Merge with Domain Precedence

When `landing` and `saas` exist in both directories:

1. **Keep both as separate packs** if use cases are distinct:
   - `packs/landing-goal/` (simple HTML/CSS landing)
   - `packs/landing-domain/` (Next.js with rules and prompts)

2. **Or merge into single pack** with type discrimination:
   - Pack includes both simple (goal) and complex (domain) configurations
   - Execution path selected based on `type` field

### Recommended Approach

Keep separate packs with naming convention:
- `landing-simple` (from goals/landing) 
- `landing-full` (from domains/landing)
- `saas-simple` (from goals/saas)
- `saas-full` (from domains/saas)

This preserves the simplicity of goal packs while maintaining the governance features of domain packs.

---

## Field Mapping

### Goals Pack Fields
```yaml
name: string              # Required
description: string       # Required
language: string          # e.g., typescript, javascript
framework: string         # e.g., express, react
files: string[]           # Files to generate
run_command: string      # How to run
verify_command: string   # How to verify
env_vars: string[]       # Environment variables
dependencies: string[]   # npm dependencies
readme_template: string  # README content
```

### Domain Pack Fields
```yaml
name: string             # Required
description: string      # Required
category: string         # frontend, backend, fullstack, web
extends: string          # Parent pack
rules: Rule[]            # Governance rules
prompts: string[]        # Prompt templates
scaffold: string[]       # File paths to scaffold
evidence: object         # Evidence requirements
instant_mode: object     # Instant mode config
```

### Unified Schema Fields
```yaml
# Required
name: string
description: string

# Common optional
category?: string
tags?: string[]

# Goal-only (type = "goal")
language?: string
framework?: string
files?: string[]
run_command?: string
verify_command?: string
env_vars?: string[]
dependencies?: string[]
readme_template?: string

# Domain-only (type = "domain")
extends?: string
rules?: Rule[]
prompts?: string[]
scaffold?: string[]
evidence?: Evidence
instant_mode?: InstantMode
```

---

## Rollback Plan

If migration fails:
1. Preserve original `packs/goals/` and `packs/domains/` as backup
2. Use git tags to mark pre-migration state
3. Restore by: `git checkout pre-migration-ref -- packs/`
