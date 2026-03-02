# OAL v1 — Standalone Orchestration Layer

**19 Hooks · 5 Core Rules · 17 Contextual Rules · 14 Agents · 16 Commands**
**19 Hooks · 5 Core Rules · 17 Contextual Rules · 14 Agents · Core + Advanced Plugin Commands**

## OAL v1 Core Additions (Implemented)

- **Policy Engine:** central policy decisions for command/file/supply-chain gating (`hooks/policy_engine.py`)
- **Trust Review:** config/hook/MCP/env risk scoring + signed manifest output (`hooks/trust_review.py`)
- **Shadow Manager:** overlay-style shadow tracking + evidence artifact helpers (`hooks/shadow_manager.py`)
- **Idea-as-Code:** template contracts for `.oal/idea.yml`, `.oal/policy.yaml`, `.oal/runtime.yaml`
- **Maintainer + Ship commands:** `/OAL:maintainer`, `/OAL:ship`
- **Platform stubs:** tri-runtime adapters, registry verifier, lab pipeline, and control-plane OpenAPI
- **Control Plane server:** lightweight local API server at `control_plane/server.py` (standard library HTTP server)
- **CLI entrypoint:** `scripts/oal.py` supports `ship/fix/secure/maintainer/trust/runtime/lab`

## What Changed from v3

| Area | v3 | v4 |
|------|----|----|
| Context injection | ~200 lines every session | ~53 lines max (70% reduction) |
| Per-prompt injection | 25 lines always | 1-8 lines, keyword-matched |
| Rules loaded | 23 always | 5 core always + 12 contextual on-demand |
| When stuck | "stop and think" | Auto-suggest /OAL:escalate to Codex or Gemini |
| Test quality | Catches fake tests | Catches fake + boilerplate + happy-path-only |
| Session transfer | Manual copy | /OAL:handoff synthesizes what+how+why |
| Skill creation | None | /OAL:learn auto-creates from patterns |
| Codex/Gemini | Manual | Auto-routing by problem domain |

## 6 Features

### Plugin Architecture (NEW)

Commands are organized into **core** and **advanced** plugins:

| Plugin | Commands | Purpose |
|--------|----------|---------|
| **core** | init, escalate, teams, ccg, crazy, compat, health-check, mode | Essential OAL functionality |
| **advanced** | deep-plan, learn, code-review, security-review, ship, handoff, maintainer, sequential-thinking, ralph-* | Specialized workflows |

**Benefits:**
- Core commands always available
- Advanced commands loaded on-demand
- Cleaner mental model
- Easier to extend

See `plugins/README.md` for full command reference.

### 1. Auto Codex/Gemini Routing

### 1. Auto Codex/Gemini Routing

Claude automatically routes problems to the right model:

```
You: "This auth middleware keeps returning 401"
→ prompt-enhancer detects "auth" → suggests: /OAL:escalate codex
→ After 3 failures, circuit-breaker auto-suggests Codex with failure context

You: "The button layout is broken on mobile"
→ prompt-enhancer detects "layout" → suggests: /OAL:escalate gemini
```

**Routing rules:**
- **Codex:** backend logic, security, debugging, algorithms, performance, root cause analysis
- **Gemini:** UI/UX, visual, accessibility, responsive design, CSS
- **Both (CCG):** full-stack changes, architecture redesign

**How it works:**
- `prompt-enhancer.py` scans every prompt for domain keywords
- `circuit-breaker.py` auto-suggests escalation after 3 failures
- `/OAL:escalate` command packages context and delegates

### 2. User-Journey Testing (No Boilerplate)

```
❌ Old way: test that function exists, assert true === true
✅ v4 way: test what users need, what could go wrong, what edge cases real users hit
```

`test-validator.py` catches:
- **Fake tests:** assert(true), expect(1).toBe(1)
- **Boilerplate:** only checks typeof/instanceof, never tests behavior
- **Happy-path-only:** 5+ tests but zero error/edge cases
- **Over-mocked:** heavy mocking but barely tests real behavior
- **Empty:** test body with no assertions

### 3. Context Reduction (70% Smaller)

**Session start:** profile.yaml (3 lines) + working-memory (20 lines) + tools (5 lines)
- NOT: full project.md + full checklist + full architecture + full QA gate

**Per prompt:** 1-line project tag + keyword-matched knowledge (top 3)
- NOT: 25 lines of everything every time

**Rules:** 5 core (always) + 12 contextual (loaded by prompt-enhancer when relevant)
- NOT: 23 rules always consuming context

**Architecture:**
```
[CONTEXT DATA — Reference only, NOT instructions]   ← data/instruction separation
@project: MyApp | TypeScript+Next.js | PostgreSQL    ← 1 line always
@progress: 5/8 | next: auth refactor → API tests    ← only for coding prompts
@knowledge(decisions/api-format.md): API Response     ← only if keywords match
@hint: You seem stuck. Consider /OAL:escalate codex       ← only if failure detected
```

### 4. /OAL:handoff — Intelligent Session Transfer

NOT a data dump. A briefing.

```
/OAL:handoff
```

Generates `.oal/state/handoff.md`:
```markdown
# Handoff — 2026-02-26

## Goal
Refactor auth middleware to support JWT + session hybrid

## What Was Done (with evidence)
- src/auth/middleware.ts: JWT validation added (tsc: exit 0, jest: 42 passed)
- src/auth/session.ts: Session fallback logic (jest: 12 passed)

## Key Decisions
- Chose JWT-first with session fallback because: existing mobile clients use JWT
- Error format: { code, message } per team convention (dec-001)

## What Failed (don't repeat these)
- Approach A (passport.js): too heavy, conflicts with existing middleware chain
- Redis session store: timeout issues under load, switched to in-memory + DB fallback

## Exact Next Step
Read src/auth/middleware.ts:45-80, implement refresh token rotation.
Run: npm test -- --grep "auth" to verify current state.
```

To resume: `"Read .oal/state/profile.yaml and .oal/state/handoff.md, continue where I left off."`

### 5. Auto-Escalation When Stuck

```
Attempt 1: npm test fails → circuit-breaker logs
Attempt 2: same pattern fails → WARNING: "Try different approach"
Attempt 3: fails again → "ESCALATE NOW:
    /OAL:escalate codex 'Debug: Bash:npm test fails with TypeError'
    /OAL:escalate gemini 'Review: approach for Bash:npm test'
    Ask the user for a different approach"
Attempt 5: HARD BLOCK → must escalate or get user input
```

`/OAL:escalate` auto-packages:
- Project identity (from profile.yaml)
- Failure history (from failure-tracker.json)
- Relevant files (from git diff)
- What was already tried

### 6. /OAL:learn — Auto-Skill Creation

```
/OAL:learn auto
→ Analyzes last 50 tool-ledger entries
→ "I noticed you create .test.ts files with the same auth+validation+edge-case pattern.
   Want me to save this as a skill?"
→ Creates ~/.config/oal/skills/api-test-pattern/SKILL.md
→ Next time you write tests, the pattern activates automatically

/OAL:learn component-scaffold
→ "Describe the pattern."
→ You: "Every React component needs index.ts, Component.tsx, Component.test.tsx, types.ts"
→ Creates skill with templates
→ Next time: auto-scaffolds
```

## Agent-Model Routing

OAL assigns specific models to **all 14** agents for optimal results:

| Agent | Provider | Model Version | Domain |
|-------|----------|--------------|--------|
| oal-frontend-designer | gemini-cli | Gemini 3.1 Pro Preview | UI/UX, CSS, responsive design |
| oal-backend-engineer | codex-cli | GPT 5.3 | APIs, logic, algorithms |
| oal-security-auditor | codex-cli | GPT 5.3 | Auth, encryption, vulnerabilities |
| oal-database-engineer | codex-cli | GPT 5.3 | SQL, migrations, schema |
| oal-testing-engineer | claude | Claude Sonnet 4 | Unit, integration, E2E tests |
| oal-infra-engineer | codex-cli | GPT 5.3 | Docker, CI/CD, deployment |
| oal-research-mode | claude | Claude Haiku 3.5 | Web search, docs lookup |
| oal-architect-mode | claude | Claude Sonnet 4 | System design, trade-offs |
| oal-implement-mode | domain-dependent | Claude Sonnet 4 (fallback) | Coding with TDD |
| oal-architect | codex-cli | GPT 5.2 | Planning, delegation |
| oal-critic | codex-cli | GPT 5.3 | Code review (3 perspectives) |
| oal-executor | claude | Claude Sonnet 4 | Implementation with evidence |
| oal-qa-tester | claude | Claude Sonnet 4 | User-journey test writing |
| oal-escalation-router | claude | Claude Haiku 3.5 | Cross-model coordination |

**How it works:**
- `prompt-enhancer.py` detects domain keywords and suggests the right agent
- `runtime/team_router.py` dispatches to codex-cli (GPT 5.3 for code, GPT 5.2 for planning) or gemini-cli (Gemini 3.1 Pro Preview) via subprocess
- Claude agents use Sonnet 4 for deep reasoning or Haiku 3.5 for fast classification
- Fallback: if preferred CLI not installed, routes to Claude native

## Cognitive Modes

Set Claude's operating mode for focused work:

```
/OAL:mode research     # Read, search, synthesize -- no code changes
/OAL:mode architect    # System design, specs only -- no implementation
/OAL:mode implement    # TDD, verify every change -- active coding
/OAL:mode clear        # Return to default behavior
```

Mode persists in `.oal/state/mode.txt`. Every prompt gets `@mode:` context injection.

## Cross-Session Memory

OAL captures and retrieves context across sessions (feature flag: `memory`):

- **Capture**: `session-end-capture.py` writes `.oal/state/memory/*.md` on session end
- **Retrieval**: `session-start.py` injects `@recent-memory:` (<=150 chars) at session start
- **Search**: `prompt-enhancer.py` injects `@memory:` (<=200 chars) when keywords match
- **Storage**: Max 50 files, auto-rotated. Plain `.md` files -- no vector DB.

Enable: set `memory: true` in `settings.json._oal.features`

## Installation

### Fresh Install
```bash
chmod +x OAL-setup.sh
./OAL-setup.sh install
```

### Upgrade from v3
```bash
# Preview what will change (no files modified)
./OAL-setup.sh install --dry-run

# Install (auto-detects v3, backs up, cleans deprecated files)
./OAL-setup.sh update

# Non-interactive (CI/CD, scripted setups)
./OAL-setup.sh update --non-interactive --merge-policy=apply   # auto-merge settings
./OAL-setup.sh update --non-interactive --merge-policy=skip    # keep existing settings
./OAL-setup.sh update --non-interactive --clear-omc            # auto-clear detected OMC artifacts
./OAL-setup.sh update --non-interactive --without-legacy-aliases  # OAL-only command surface

# Clean reinstall / uninstall
./OAL-setup.sh reinstall
./OAL-setup.sh uninstall
```

If legacy OMC installation signals are detected in `~/.claude`, the setup flow now prints a warning with possible outcomes and handling choices (keep, clear, cancel) before proceeding.

**What the installer handles on v3 → v4 upgrade:**

| Action | Files |
|--------|-------|
| **Remove** 23 v3 rules | 00-truth-evidence.md through 22-auto-plugin-mcp.md |
| **Remove** 5 deprecated agents | cross-validator, dependency-guardian, infra-guardian, perf-analyst, ui-reviewer |
| **Remove** 2 deprecated commands | cross-review.md, simplify.md |
| **Remove** stale cache | hooks/__pycache__/, *.pyc |
| **Install** 5 core rules | 00-truth through 04-testing |
| **Update** 11 hooks | All rewritten for lean context + auto-escalation |
| **Install** 5 agents | oal-executor, oal-architect, oal-critic, oal-qa-tester, oal-escalation-router |
| **Install** OAL commands + OMC parity aliases | OAL-prefixed commands plus auto-generated legacy OMC-compatible aliases in `~/.claude/commands` (disable with `--without-legacy-aliases`) |
| **Merge** settings.json | Interactive preview before merging |
| **Backup** everything | ~/.claude/.oal-backup-[timestamp]/ |

### After Install
```bash
cd your-project
/OAL:project-init    # Creates .oal/state/profile.yaml + knowledge/
/OAL:health-check    # Verifies everything works
```

### Backward Compatibility
- Legacy `.omc/*` projects auto-migrate into `.oal/state/*` on first run
- Run `/OAL:init` to force migration and create missing standalone state files

## File Structure

```
oal/
├── hooks/                    # 19 Python hooks (8 events)
│   ├── session-start.py      # Lean context injection + memory retrieval
│   ├── session-end-capture.py # Memory + learnings capture on session end
│   ├── prompt-enhancer.py    # Keyword retrieval + auto-escalation hints
│   ├── circuit-breaker.py    # Failure tracking + auto-escalation
│   ├── test-validator.py     # User-journey test quality
│   ├── firewall.py           # Command security (enterprise-hardened)
│   ├── secret-guard.py       # File access security
│   ├── tool-ledger.py        # Activity logging (with rotation)
│   ├── post-write.py         # Secret detection in written files
│   ├── quality-runner.py     # QA gate enforcement
│   ├── stop-gate.py          # Evidence verification on completion
│   ├── stop_dispatcher.py    # Stop hook orchestrator
│   ├── pre-compact.py        # State preservation before compaction
│   ├── pre-tool-inject.py    # Per-tool context injection
│   ├── post-tool-failure.py  # Failure capture + circuit-breaker feed
│   ├── config-guard.py       # Settings/config mutation guard
│   ├── policy_engine.py      # Central policy decisions
│   ├── trust_review.py       # Config/hook/MCP risk scoring
│   ├── shadow_manager.py     # Shadow tracking + evidence helpers
│   ├── _common.py            # Shared utilities (json_input, block_decision)
│   ├── _budget.py            # Token budget constants
│   ├── _memory.py            # Memory read/write helpers
│   ├── _learnings.py         # Learnings capture helpers
│   ├── _agent_registry.py    # Agent-model routing registry
│   └── state_migration.py    # .omc/* → .oal/state/* migration
│
├── rules/
│   ├── core/                 # 5 rules -- ALWAYS loaded
│   │   ├── 00-truth.md       # Never claim unverified state
│   │   ├── 01-surgical.md    # Minimal changes + active planning
│   │   ├── 02-circuit-breaker.md  # 2-strike rule + escalation
│   │   ├── 03-ensemble.md    # Codex/Gemini/CCG routing
│   │   └── 04-testing.md     # User-journey testing standard
│   │
│   └── contextual/           # 17 rules -- loaded when relevant
│       ├── doc-check.md      # Read arch docs before edits
│       ├── big-picture.md    # System map before coding
│       ├── outside-in.md     # Debug from user perspective
│       ├── infra-safety.md   # --dry-run, no hardcoded secrets
│       ├── dependency-safety.md  # Evaluate before adding deps
│       ├── context-management.md # /OAL:handoff over /compact
│       ├── context-minimization.md # Token budget enforcement
│       ├── code-hygiene.md   # No unnecessary code, no noise comments
│       ├── security-domains.md # Auth/payment/DB code review gate
│       ├── ddd-sdd.md        # Domain-driven scaffolding rules
│       ├── web-search.md     # When/how to use web search
│       ├── vision-detection.md # Screenshot/image signal detection
│       ├── research-mode.md  # Research mode constraints
│       ├── architect-mode.md # Architect mode constraints
│       ├── implement-mode.md # Implement mode + TDD enforcement
│       ├── persistent-mode.md # ulw/ralph persistent work mode
│       └── write-verify.md   # Write-then-verify discipline
│
├── agents/                   # 14 agents
│   ├── oal-executor.md           # Implements with evidence
│   ├── oal-architect.md          # Plans + routes to Codex/Gemini
│   ├── oal-critic.md             # 3-perspective review (no LGTM)
│   ├── oal-qa-tester.md          # User-journey test writer
│   ├── oal-escalation-router.md  # Cross-model coordinator
│   ├── oal-frontend-designer.md  # UI/UX (gemini-cli)
│   ├── oal-backend-engineer.md   # APIs + logic (codex-cli)
│   ├── oal-security-auditor.md   # Auth + vulns (codex-cli)
│   ├── oal-database-engineer.md  # SQL + migrations (codex-cli)
│   ├── oal-testing-engineer.md   # Unit/integration/E2E (claude)
│   ├── oal-infra-engineer.md     # Docker + CI/CD (codex-cli)
│   ├── oal-research-mode.md      # Web search + docs (claude)
│   ├── oal-architect-mode.md     # System design (claude)
│   └── oal-implement-mode.md     # TDD coding (domain-dependent)
│
├── commands/                 # 16 commands (OAL: prefixed)
│   ├── OAL:init.md          # /OAL:init -- unified initializer
│   ├── OAL:project-init.md  # /OAL:project-init -- alias for init
│   ├── OAL:health-check.md  # /OAL:health-check -- verify setup
│   ├── OAL:handoff.md       # /OAL:handoff -- intelligent session transfer
│   ├── OAL:escalate.md      # /OAL:escalate -- route to Codex/Gemini
│   ├── OAL:learn.md         # /OAL:learn -- auto-create skills
│   ├── OAL:crazy.md         # /OAL:crazy -- max multi-agent orchestration
│   ├── OAL:deep-plan.md     # /OAL:deep-plan -- strategic planning
│   ├── OAL:code-review.md   # /OAL:code-review -- two-pass review
│   ├── OAL:domain-init.md   # /OAL:domain-init -- DDD scaffolding
│   ├── OAL:security-review.md # /OAL:security-review -- vuln scan + audit
│   ├── OAL:ship.md          # /OAL:ship -- idea to evidence to PR
│   ├── OAL:maintainer.md    # /OAL:maintainer -- OSS maintainer kit
│   ├── OAL:mode.md          # /OAL:mode -- set cognitive mode
│   ├── OAL:ralph-start.md   # /OAL:ralph-start -- start autonomous loop
│   └── OAL:ralph-stop.md    # /OAL:ralph-stop -- stop autonomous loop
│
├── templates/
│   ├── profile.yaml          # Project identity template
│   └── working-memory.md     # Working memory template
│
├── scripts/
│   └── settings-merge.py     # Safe settings.json merger
│
├── settings.json             # Hook config + permissions
├── OAL-setup.sh              # Unified setup manager (install/update/reinstall/uninstall)
└── install.sh                # Deprecated wrapper (for backward compatibility)
```

## Project Structure After /OAL:project-init

```
your-project/
└── .oal/
    ├── state/
    │   ├── profile.yaml
    │   ├── working-memory.md
    │   ├── handoff.md
    │   ├── quality-gate.json
    │   ├── _plan.md
    │   ├── _checklist.md
    │   └── ledger/
    │       ├── tool-ledger.jsonl
    │       └── failure-tracker.json
    ├── knowledge/
    │   ├── decisions/
    │   ├── conventions/
    │   ├── rules/
    │   └── invariants.md
    ├── trust/
    ├── evidence/
    ├── shadow/
    └── migrations/
```

## Design Principles (from RAG/MCP Framework)

1. **Data ≠ Instructions:** Context injected as `[CONTEXT DATA]`, never mixed with rules
2. **Retrieve, don't stuff:** Keyword match → top-3 knowledge chunks, not everything
3. **Metadata matters:** Decisions have date + confidence + source
4. **Evidence-based output:** Every completion includes Verified/Unverified/Assumptions
5. **Escalate, don't loop:** Codex for logic, Gemini for visuals, user for decisions
6. **Skills evolve:** Repetitive patterns become auto-activating skills

## Hardening (v4.1)

**Verification enforcement:** `stop-gate.py` blocks completion if code was modified but no verification commands were run — regardless of whether `quality-gate.json` exists. This prevents "done" claims without evidence.

**Multilingual prompts:** `prompt-enhancer.py` detects coding/stuck/UI/security signals in both English and Korean. Knowledge search extracts both Latin and Hangul tokens. Set `locale_hint` in `profile.yaml` to optimize (default: `auto`).

**Secret guard policy:** `.env.example`, `.env.sample`, `.env.template` are readable (for reference) but cannot be modified. All other `.env*` files remain fully blocked.

**Non-interactive install:** `./OAL-setup.sh update --non-interactive --merge-policy=apply|skip` for CI/CD and scripted setups. `--dry-run` guarantees zero file changes.

## Cross-Platform Session Transfer

OAL supports transferring sessions between Claude Code and Claude.ai (or any AI chat).

**Claude Code → Claude Code (same machine):**
```
> /OAL:handoff
(new session)
> Read .oal/state/profile.yaml and .oal/state/handoff.md, continue where I left off.
```

**Claude Code → Claude.ai (or any other platform):**
```
> /OAL:handoff
(Claude generates both .oal/state/handoff.md AND .oal/state/handoff-portable.md)
(Claude shows you the portable version in the terminal)
(Copy the portable version → paste into Claude.ai)
```

The **portable** version is self-contained: project identity, decisions, failures, and critical code context are all inline. No file references that the next AI can't access.

**Auto-generated on compaction:** `pre-compact.py` automatically generates both handoff files before context compaction, so your state is always recoverable even if you don't run `/OAL:handoff`.

## Standalone Architecture

OAL runs as a standalone system. OMC is no longer required.

- **No OMC dependency:** all hooks, HUD, and commands run independently. Legacy `vendor/omc` kept for reference only.
- **Router strategy:** OAL provides internal routing via `/OAL:teams` and `/OAL:ccg`.
- **State strategy:** canonical runtime state is `.oal/state/*` with one-time auto-migration from legacy `.omc/*`.
- **Crash isolation:** all OAL hooks exit 0 on internal errors to avoid sibling-hook crashes.
- **Legacy skill bridge:** `python3 scripts/oal.py compat list|run` supports all vendored legacy skill names through OAL-native handlers.
  - Contract introspection: `python3 scripts/oal.py compat contract --all`
  - Contract snapshot export: `python3 scripts/oal.py compat snapshot --output runtime/oal_compat_contract_snapshot.json`
  - Snapshot drift check: `python3 scripts/check-oal-compat-contract-snapshot.py --strict-version`
  - Standalone naming check: `python3 scripts/check-oal-standalone-clean.py`
  - Gap report: `python3 scripts/oal.py compat gap-report` (writes `.oal/evidence/oal-compat-gap.json`)
  - GA gate: `python3 scripts/oal.py compat gate --max-bridge 0` (fails if bridge skills remain)
  - Native-promoted coverage: all 37 legacy skill names are mapped to native OAL handlers (`bridge=0` in gap-report)
  - No-vendor verification: `./scripts/verify-standalone.sh`

## v1.0.0

Initial release.

## Command Reference

All commands are prefixed with `OAL:` for easy discovery. Type `/OAL:` in Claude Code to see all available commands.

### /OAL:init — Unified Project & Domain Initializer

Auto-detects what's needed and runs the right initialization.

**Auto-detection:**
- No argument + no `.oal/state` → **Project Init** (creates profile, quality gate, knowledge dir)
- Argument is a domain name → **Domain Init** (DDD scaffolding from existing patterns)
- `.oal/state` already exists → **Health Check** (verifies setup, offers upgrades)

**When to use:** Start of any project or when adding a new domain module.

```
> /OAL:init                    ← auto-detect (project setup or health check)
> /OAL:init payment            ← create new "payment" domain
> /OAL:init user-profile       ← create new "user-profile" domain
```

**Aliases:** `/OAL:project-init` and `/OAL:domain-init` redirect to this command.

---

### /OAL:crazy — Maximum Multi-Agent Orchestration

Activates all available agents in parallel for maximum throughput.

**How it works:**
1. **Intent Classification** — Asks "I understand you want to [FIX/IMPLEMENT/REFACTOR/REVIEW]" before acting
2. **Agent Dispatch** — Claude orchestrates, Codex does deep code + review, Gemini handles UI/UX
3. **Anti-Hallucination** — Every change must have exit-code evidence; no "looks correct" claims
4. **Error Loop Prevention** — After 3 identical failures, forces escalation or different approach
5. **Completion Gate** — Won't stop until build passes, tests pass, no TODOs left

**When to use:** Complex tasks that benefit from multiple perspectives, or when you want maximum quality.

```
> /OAL:crazy implement user authentication with OAuth2
> /OAL:crazy fix all failing tests in the payment module
```

**Quick mode:** Just type `crazy` anywhere in your prompt — the prompt-enhancer auto-detects it.

---

### /OAL:deep-plan — Strategic Planning with Intent Understanding

Creates a phased implementation plan by understanding WHY you want something, not just WHAT.

**How it works:**
1. **Direction Discovery** — Asks 2-3 focused questions about your goal and constraints
2. **Domain Mapping** — Scans existing codebase for patterns, conventions, related code
3. **Plan Generation** — Multi-phase plan with dependencies, risks, and effort estimates
4. **Checklist Creation** — Writes `.oal/state/_checklist.md` for progress tracking

**When to use:** Before starting any non-trivial feature. Especially when the scope is unclear.

```
> /OAL:deep-plan add real-time notifications
> /OAL:deep-plan migrate from REST to GraphQL
```

---

### /OAL:escalate — Delegate to Specialist Agents

Routes tasks to the best-suited agent (Codex, Gemini, or others).

**How it works:**
1. Identifies the task type (code, design, architecture, debugging)
2. Selects the appropriate agent based on the task
3. Provides structured context (files, patterns, constraints) to the agent
4. Returns results with verification

**Usage patterns:**
```
> /OAL:escalate codex "debug the memory leak in worker.ts"
> /OAL:escalate codex "security audit of auth/ directory"
> /OAL:escalate gemini "review the dashboard layout for accessibility"
> /OAL:escalate gemini "improve the mobile responsive design"
```

---

### /OAL:security-review — Vulnerability Scanner + Deep Review

Automated security scanning with optional Codex deep audit.

**How it works:**
1. **Automated scan** — 6 grep-based checks:
   - Hardcoded secrets (22 patterns: AWS, Google, Stripe, Firebase, etc.)
   - SQL injection (string concatenation in queries)
   - XSS vulnerabilities (innerHTML, dangerouslySetInnerHTML)
   - Auth bypass risks (missing middleware, unprotected routes)
   - Path traversal (unsanitized file paths)
   - Sensitive data exposure (logging PII, missing encryption)
2. **URI hardening checklist** — CORS, CSP, HTTPS, rate limiting, redirect validation
3. **Codex deep review** — Escalates critical files for line-by-line security audit

**When to use:** Before deploying auth, payment, or database code. After any security-related changes.

```
> /OAL:security-review
> /OAL:security-review src/auth/
```

---

### /OAL:code-review — Two-Pass Code Review

Combines line-by-line precision with whole-file structural analysis.

**How it works:**
1. **Pass 1: Line-by-Line** — Reviews every line for: dead code, noise comments, unused imports, magic numbers, error handling gaps, type safety issues
2. **Pass 2: Structural** — Reviews file-level concerns: naming consistency, function length, separation of concerns, dependency direction, test coverage gaps

**When to use:** Before merging any significant change. For periodic codebase hygiene.

```
> /OAL:code-review src/payment/checkout.ts
> /OAL:code-review   (reviews recent changes)
```

---

### /OAL:domain-init — DDD Domain Scaffolding (alias for /OAL:init)

Now an alias for `/OAL:init [domain-name]`. See /OAL:init above.

```
> /OAL:init orders             ← using existing domain as reference
> /OAL:domain-init orders      ← same thing (alias)
```

---

### /OAL:handoff — Session Transfer

Saves your current working context for the next Claude Code session.

**How it works:**
1. Captures: what was done, current state, what failed, exact next step
2. Writes `.oal/state/handoff.md` (full context) and `.oal/state/handoff-portable.md` (compact, for Claude.ai)
3. Next session auto-detects handoff file and injects context via `session-start.py`

**When to use:** At the end of every work session, or before switching to a different task.

```
> /OAL:handoff
> /OAL:handoff "stopped at payment integration, Stripe webhook failing"
```

---

### /OAL:learn — Auto-Create Reusable Skills

Detects repeated patterns and turns them into Claude Code skills.

**How it works:**
1. **Auto-detect** — Analyzes recent tool usage for repeated patterns
2. **Extraction** — Asks what the pattern is and when it should trigger
3. **Skill creation** — Writes a `.md` skill file to `.claude/commands/` or `.oal/skills/`
4. **Activation** — Skill activates automatically on matching future prompts

**When to use:** When you notice yourself doing the same thing repeatedly.

```
> /OAL:learn   (auto-detects from recent work)
> /OAL:learn api-error-handling   (manual: names the skill)
```

---

### /OAL:health-check — Verify OAL Installation

Tests that all OAL components are working correctly.

**How it works:**
1. Checks: hooks installed and syntax-valid, rules loaded, agents available
2. Checks: settings.json has OAL hook registrations
3. Checks: `.oal/` project setup (state, quality-gate, knowledge)
4. Reports any missing or broken components

**When to use:** After installation, after upgrades, or when something seems wrong.

```
> /OAL:health-check
```

---

### Quick Modes (No Command Needed)

These are detected automatically by the prompt-enhancer — just include the keyword in any message:

| Keyword | Mode | Behavior |
|---------|------|----------|
| `ulw` / `ultrawork` / `ralph` | **Persistent** | Doesn't stop until checklist is complete. Skips blocked items, returns later. |
| `crazy` / `모든 에이전트` | **All-Agent** | Claude+Codex+Gemini parallel dispatch. Maximum orchestration. |
| `끝까지` / `don't stop` | **Persistent** | Korean/English variants of persistent mode. |

```
> ulw fix all the failing tests
> crazy implement the entire auth system
> ralph 모든 버그 수정해
```

## Compatibility

- **Claude Code:** Full support (hooks, rules, agents, commands)
- **Standalone mode:** No OMC installation required
- **Legacy aliases:** Full OMC-compatible command aliases are installed in `~/.claude/commands` by default (disable with `--without-legacy-aliases`)
- **Superpowers plugin:** Compatible — OAL handles quality gates, Superpowers handles TDD workflow
- **Claude-Mem plugin:** Compatible — OAL handles structured knowledge, Claude-Mem handles session memory
- **Claude native auto-memory:** Compatible — OAL profile/state complements MEMORY.md

## Ecosystem Powerpack (New)

OAL now includes an **ecosystem sync layer** to pull and operationalize external plugin ecosystems as optional upstream references.

### CLI

```bash
python3 scripts/oal.py ecosystem list
python3 scripts/oal.py ecosystem status
python3 scripts/oal.py ecosystem sync --names superpowers,ralph-wiggum,claude-flow,claude-mem,memsearch,beads,planning-with-files,hooks-mastery,compound-engineering
```

### What sync does

- Clones selected repos into `vendor/ecosystem/*` (shallow by default)
- Writes lock metadata to `.oal/state/ecosystem-lock.json`
- Writes per-repo integration notes into `.oal/knowledge/ecosystem/*.md`
- Exposes new compat skill names mapped to native OAL routes:
  - `superpowers`, `ralph-wiggum`, `claude-flow`, `claude-mem`, `memsearch`, `beads`, `planning-with-files`, `hooks-mastery`, `compound-engineering`
