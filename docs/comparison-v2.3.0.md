# OMG v2.3.0 — Deep Competitive Analysis

> Generated: 2026-03-21 | Method: CRAZY mode 5-track parallel research

## Frameworks Compared

| Framework | Repo | Version | License | Stars |
|---|---|---|---|---|
| **OMG** | trac3r00/OMG | 2.3.0 | MIT | New |
| **Superpowers** | obra/superpowers | 5.0.5 | MIT | ~100K |
| **oh-my-claudecode (OMC)** | Yeachan-Heo/oh-my-claudecode | 4.9.0 | MIT | 10.7K |
| **oh-my-openagent** | code-yeongyu/oh-my-openagent | 3.12.x | SUL-1.0 | 41.9K |
| **oh-my-codex (OMX)** | Yeachan-Heo/oh-my-codex | 0.11.x | MIT | 2.3K |

---

## 1. Architecture

### OMG — Governance-First Control Plane

- **Middleware architecture**: sits between host and tools, intercepting every tool call
- **Production MCP server** (`omg-control`) with OpenAPI spec, stdio-first
- **Encrypted, namespaced memory** with state migration
- **Contract compiler**: generates host-specific artifacts for Claude, Codex, Gemini, Kimi
- **Dual distribution**: npm (`@trac3r/oh-my-god`) + pip (`oh-my-god`)
- **Mutation Gate**: intercepts risky filesystem operations before execution
- **Proof Gate + Claim Judge**: requires machine-generated evidence for any "done" claim
- **Language**: Python + Shell
- **Scale**: ~228K LOC, 54 hooks, 39 agents, 37 commands, 290 test files

### Superpowers — Skills-First Methodology Injection

- **Auto-updating skills repo** cloned locally, `git pull` on every session start
- **7-phase workflow** hardcoded: Brainstorm → Worktree → Plan → Execute → TDD → Review → Complete
- **14 canonical skills** in a separate repository (`obra/superpowers-skills`)
- Skills activate automatically via mandatory first-response protocol
- **Marketplace ecosystem**: core plugin, lab, chrome, developing-for-claude-code repos
- **Anthropic-verified** plugin (accepted January 15, 2026), 233,901 marketplace installs
- **Language**: Shell 57.8%, JavaScript 30.1%, HTML 4.5%, Python 3.9%, TypeScript 2.9%
- **Brainstorm server**: Node.js with vendored `node_modules` (no runtime npm required)

### oh-my-claudecode — Teams-First Delegation

- **Three-layer skill composition**: Execution + Enhancement + Guarantee
- **Real tmux pane management** for parallel worker visualization
- **Model tiering**: Haiku (LOW), Sonnet (MEDIUM), Opus (HIGH) with automatic routing
- **7 orchestration modes**: Team, Autopilot, Ultrapilot, Swarm, Pipeline, Ralph, Ultrawork
- **Magic keywords** for natural-language mode switching
- **State management**: Local (`.omc/state/`), Global (`~/.omc/state/`), legacy auto-migration
- **31 lifecycle hooks** covering UserPromptSubmit, Stop, PreToolUse, PostToolUse
- **npm package**: `oh-my-claude-sisyphus`

### oh-my-openagent — Tool-Innovation Pioneer

- **OpenCode plugin** (not Claude Code native — requires OpenCode as host)
- **11 mythologically-named agents** (Sisyphus, Hephaestus, Prometheus, Oracle, Librarian, Explore, Atlas, Metis, Momus, Multimodal-Looker, Sisyphus-Junior)
- **Hashline edit tool**: tags every line with a 4-char content hash, stale edits rejected. Claimed **6.7% → 68.3% edit success improvement**
- **Full LSP client**: rename, goto-def, find-refs, diagnostics, workspace symbol search
- **AST-grep**: pattern-aware search/rewrite across 25 languages via `@ast-grep/napi`
- **Dual-prompt architecture**: different system prompts per model family (Claude vs GPT), auto-detected at runtime
- **Skill-scoped MCP servers**: spin up on-demand per skill, shut down after
- **Language**: TypeScript (~6MB), compiles to Bun binaries for all major platforms
- **Self-developing**: partially writes its own code via Sisyphus agent (CI includes `sisyphus-agent.yml`)

### oh-my-codex — Codex-Native Wrapper

- **Thin wrapper** around OpenAI Codex CLI ("Codex as execution engine, OMX as the brain")
- **Rust runtime component** (v0.11.0+) for tmux pane resolution and stability
- **5 built-in MCP servers**: state, code intel (LSP), AST manipulation, notepad, Python REPL
- **Worktree-first teams**: each worker gets isolated git worktree at `.omx/team/<name>/worktrees/worker-N`
- **Multi-provider team mixing**: `OMX_TEAM_WORKER_CLI_MAP` for per-worker backend selection
- **Three model lanes**: `OMX_DEFAULT_FRONTIER_MODEL`, `OMX_DEFAULT_STANDARD_MODEL`, `OMX_DEFAULT_SPARK_MODEL`
- **Language**: TypeScript + Rust (5% of codebase)

---

## 2. Features Comparison

### Agent Counts and Models

| Framework | Agent Count | Model Strategy |
|---|---|---|
| OMG | 39 | Role-based YAML config (Opus/Sonnet/Haiku) |
| Superpowers | ~5 (dispatch-based) | Skill-driven, inherits host model |
| OMC | 29-32 | Three-tier (LOW/MEDIUM/HIGH) |
| oh-my-openagent | 11 | Per-agent multi-provider (Claude/GPT/Kimi/Gemini/Grok/MiniMax) |
| OMX | 30+ across 5 lanes | Three-lane env var config |

### Orchestration Modes

| Mode | OMG | Superpowers | OMC | OpenAgent | OMX |
|---|---|---|---|---|---|
| Sequential | Yes | Yes (7-phase) | Autopilot | Sisyphus | $autopilot |
| Parallel agents | /OMG:crazy | /execute-plan | Ultrapilot/Ultrawork | ultrawork/ulw | $ultrawork |
| Team (tmux) | /OMG:teams | No | Team (real panes) | Background agents (tmux) | omx team N:role |
| Persistent loop | /OMG:ralph-start | No | Ralph | Ralph Loop | $ralph |
| Multi-model | /OMG:ccg, /OMG:escalate | No | omc ask | Built-in per-agent | omx ask |
| Swarm | No | No | Swarm | No | No |
| Pipeline | No | No | Pipeline | No | No |
| Deep planning | /OMG:deep-plan | /write-plan | deep-interview | Prometheus+Metis+Momus | omx deep-interview |

### Slash Commands / Skills

| Framework | Count | Invocation |
|---|---|---|
| OMG | 37 commands | `/OMG:<name>` |
| Superpowers | 14 skills | Auto-activated or `/skill-name` |
| OMC | 34+ skills | Magic keywords or `/skill` CLI |
| oh-my-openagent | ~15 skills | Keyword triggers |
| OMX | 36+ skills | `$skillname` in session |

### Hooks

| Framework | Count | Key Hooks |
|---|---|---|
| OMG | 54 | circuit-breaker, firewall, stop-gate, proof-gate, secret-guard, budget-governor, prompt-enhancer, quality-runner, test-validator, tool-ledger |
| Superpowers | ~3 | SessionStart (skills init) |
| OMC | 31 | UserPromptSubmit (keyword detection), Stop (continuation), PreToolUse (validation), PostToolUse (recovery) |
| oh-my-openagent | 50+ | Context compaction, todo enforcement, comment quality, edit error recovery, JSON recovery, notifications, model fallback |
| OMX | ~20 | Lifecycle events, team coordination |

### Host Support

| Host | OMG | Superpowers | OMC | OpenAgent | OMX |
|---|---|---|---|---|---|
| Claude Code | Canonical | Marketplace (verified) | Primary | Compat layer | No |
| Codex CLI | Canonical | Install guide | No | No | Primary |
| Gemini CLI | Canonical | GEMINI.md guide | No | No | No |
| Kimi CLI | Canonical | No | No | No | No |
| OpenCode | Compat-only | Install guide | No | Primary | No |
| Cursor | No | Marketplace | No | No | No |

### Unique Features Per Framework

**OMG Only:**
- Production control-plane contract (`OMG_COMPAT_CONTRACT.md`)
- Contract compiler (`npx omg contract compile --host claude --host codex`)
- Release surface registry and readiness checks
- Budget governor with cost envelopes
- Encrypted namespaced memory store
- Mutation Gate (intercepts risky filesystem ops)
- Forge orchestration engine
- Lab domain packs (robotics, vision, ML)
- Adoption system (detects OMC/OMX/Superpowers installations)

**Superpowers Only:**
- Mandatory TDD enforcement (RED-GREEN-REFACTOR or code is deleted)
- Socratic Brainstorming phase with Cialdini persuasion principles
- Self-updating decoupled skills (git pull on session start)
- Skills can author new skills (recursive self-improvement)
- Severity-based code review blocking (critical = halt)
- Anthropic-verified marketplace status

**OMC Only:**
- 7 distinct orchestration modes (most in class)
- Anti-slop workflow (v4.7.9) for detecting/cleaning AI-generated low-quality code
- `omc session search` with time filters (session history as searchable DB)
- `omc wait` rate-limit detection with auto-resume daemon
- AWS Bedrock model routing (v4.7.10+)
- OpenClaw gateway integration for enterprise event forwarding

**oh-my-openagent Only:**
- Hashline edit validation (content-hash anchored, 6.7%→68.3% improvement)
- Dual-prompt architecture (per-model-family system prompts)
- Skill-scoped MCP servers (on-demand spin-up/teardown)
- Anti-delegation architecture (Sisyphus-Junior cannot re-delegate)
- `/init-deep` hierarchical AGENTS.md generation
- IntentGate pre-execution analysis
- Claude Code compatibility layer (imports CC hooks/commands/MCPs into OpenCode)

**OMX Only:**
- Cross-provider team mixing at worker level (codex+claude+gemini in same team)
- Rust runtime for hot-path stability (tmux pane resolution)
- Worktree-isolated team workers with auto merge strategy selection
- `--yolo` through `--madmax` reasoning depth flags
- State persistence via MCP servers (not flat files)

---

## 3. Production Readiness

### Testing and CI

| Framework | Test Files | Test Framework | CI Workflows | Coverage Reporting |
|---|---|---|---|---|
| OMG | **290** | pytest (parallel, xdist) | 4 (compat-gate, publish, release, gitguardian) | term-missing across 8 modules |
| Superpowers | Present (6 dirs) | Unknown | **None** | None |
| OMC | Present | Vitest | 7 (CI, PR, Release, Labels, Stale, Copilot review, Cleanup) | No published metric |
| oh-my-openagent | Co-located `*.test.ts` | Bun test | 6 (ci, publish, platform-publish, sisyphus-agent, cla, lint-workflows) | None published |
| OMX | Present | Node test runner + c8 | PR gates (build+test+lint) | `coverage:team-critical` gate on high-risk modules |

### Versioning and Stability

| Framework | Version | Maturity Signal | Release Velocity |
|---|---|---|---|
| OMG | 2.3.0 | Beta (pyproject classifiers) | 721 commits in ~20 days |
| Superpowers | 5.0.5 | 5 majors in 5 months | Multiple per week |
| OMC | 4.9.0 | v3→v4 overhaul done, v4→v5 planned | 10 releases in 2 weeks |
| oh-my-openagent | 3.12.3 | v3.3→v3.12 in 40 days | 30 releases in 40 days |
| OMX | 0.11.4 | Pre-1.0 | 68 total releases, same-day hotfixes |

### Documentation

| Framework | README | Reference Docs | Architecture Docs | Multi-language | Website |
|---|---|---|---|---|---|
| OMG | Yes | QUICK-REFERENCE.md, PRESET-REFERENCE.md | Mermaid diagrams in README | No | No |
| Superpowers | Yes | RELEASE-NOTES, CHANGELOG | DeepWiki guide | No | Anthropic plugin page |
| OMC | Yes | docs/REFERENCE.md | docs/ARCHITECTURE.md | Japanese | ohmyclaudecode.com |
| oh-my-openagent | Yes | docs/reference/features.md | Per-directory AGENTS.md | 5 languages (EN/KR/JP/ZH/RU) | ohmyopenagent.com |
| OMX | Yes | DEMO.md, CONTRIBUTING.md | prompt-guidance-contract.md | 13 languages | yeachan-heo.github.io/oh-my-codex-website |

### Security

| Framework | Dedicated Security Tooling |
|---|---|
| OMG | Firewall, secret audit, credential store, security validators, trust review, security-check pipeline, `/OMG:security-check` command |
| Superpowers | OWASP Top 10 in code review skill |
| OMC | 21 CVEs patched in v4.8.0, SSRF/path traversal checks (v4.8.1), security-reviewer agent (Opus-tier) |
| oh-my-openagent | SSRF/path traversal checks, IntentGate |
| OMX | Minimal |

---

## 4. Community and Ecosystem

| Metric | OMG | Superpowers | OMC | OpenAgent | OMX |
|---|---|---|---|---|---|
| GitHub Stars | New | ~96-102K | 10.7K | 41.9K | 2.3K |
| Forks | — | ~8.1K | 739 | 3,126 | 137 |
| Open Issues | — | 69 | 16 | 436 | — |
| Marketplace Installs | — | 233,901 | — | — | — |
| NPM Downloads | — | — | — | — | ~3,300/week |
| Satellite Repos | — | 5 (marketplace, lab, skills, chrome, dev-docs) | — | — | — |
| Discord/Community | — | Active | Active | Active | — |
| Media Coverage | — | Multiple guides/reviews | 60+ articles | Multi-language docs | LinkedIn posts |
| Contributor Concentration | Solo | Solo (Jesse Vincent) | Primary (Yeachan-Heo) | Primary (code-yeongyu) | Solo (Yeachan-Heo) |

### Relationship Map

- **oh-my-claudecode** and **oh-my-codex** are by the **same author** (Yeachan-Heo / "Bellman")
- **oh-my-openagent** (code-yeongyu) shares significant DNA with OMC (Ralph, Ultrawork, magic keywords, tmux workers) but is a separate project
- **OMG** explicitly detects and adopts from OMC, OMX, and Superpowers installations
- **Superpowers** is the only Anthropic-verified plugin among all five

---

## 5. Weaknesses

### OMG
- Heavyweight (228K LOC) — complex setup, steep learning curve
- Newer community, fewer stars
- Python+Shell dual-stack increases maintenance surface
- 721 commits in 20 days suggests high velocity but potential instability

### Superpowers
- **No automated CI** on the core repo (no `.github/workflows/`)
- 10-20 minute overhead per session (brainstorming + planning, even for trivial tasks)
- Agent autonomy calibration: blazes through without pausing on incorrect assumptions
- `superpowers-skills` community repo archived — centrally maintained only
- 5 major versions in 5 months (frequent breaking changes)
- No budget/cost tracking
- No multi-agent orchestration (beyond subagent dispatch)
- Token consumption not documented

### oh-my-claudecode
- Rapid version churn (10 releases in 2 weeks)
- npm package named `oh-my-claude-sisyphus` (discoverability friction)
- Claude Code-only host lock-in
- Orphaned agent processes and duplicate worker instances (#1 issue theme)
- State file persistence bugs causing cascading hook re-executions
- No published test coverage metric
- v4→v5 migration "coming soon" — another breaking change ahead

### oh-my-openagent
- **SUL-1.0 license (non-commercial)** — disqualifies enterprise/commercial use without negotiation
- **OpenCode-only** — not Claude Code or Codex native
- Anthropic blocking risk (OpenCode was targeted for ToS violation)
- 436 open issues, active regressions (subagent cancellation, context identity loss, model config ignored)
- Partially AI-self-developed (quality concerns)
- 7-provider subscription maze for full setup
- GPT-native agents have no Claude fallback
- References bleeding-edge/unreleased model IDs
- Sole maintainer concentration (2,334 of commits)

### oh-my-codex
- Pre-1.0 (version 0.11.x — API surface unstable)
- Codex-only host lock-in
- Single maintainer (effectively a side project)
- 137 forks / 2.3K stars — thin contributor base
- 5 MCP servers creates operational complexity (failures require `omx cleanup`)
- No test suite for 30 prompts and 39 skills (text files with no validation)
- tmux hard dependency (non-starter in containers without terminal multiplexers)
- GPT-5.4 behavior contracts require re-validation on model updates

---

## 6. Best-in-Class by Category

| Category | Winner | Runner-up | Why |
|---|---|---|---|
| Community Adoption | **Superpowers** | oh-my-openagent | ~100K stars, 233K installs, Anthropic-verified |
| Governance & Safety | **OMG** | OMC | Only framework with mutation gates, proof gates, claim judge, policy engine, trust review, production control-plane contract |
| Methodology Discipline | **Superpowers** | OMG | Mandatory TDD, Socratic brainstorming, 7-phase workflow, Cialdini-informed compliance |
| Multi-Agent Orchestration | **OMC** | oh-my-openagent | 7 modes (Team/Autopilot/Ultrapilot/Swarm/Pipeline/Ralph/Ultrawork), real tmux teams |
| Tool Innovation | **oh-my-openagent** | OMG | Hashline edits, full LSP, AST-grep, dual-prompt, skill-scoped MCPs |
| Multi-Host Parity | **OMG** | Superpowers | 4 canonical hosts + contract compiler; Superpowers covers 5 but without behavioral contracts |
| Ease of Setup | **Superpowers** | OMC | 1 command marketplace install, auto-updating, zero config |
| Testing Infrastructure | **OMG** | OMX | 290 test files, parallel execution, coverage across 8 modules |
| Security Tooling | **OMG** | OMC | Firewall + secret audit + credential store + validators + trust review + security-check pipeline |
| Cost Awareness | **OMG** | OMC | Budget governor, envelopes, cost ledger, token counter, /OMG:cost |
| Documentation Breadth | **Superpowers** | oh-my-openagent | 42+ dev docs, multi-platform guides, DeepWiki; OpenAgent has 5 languages |
| Production Contract | **OMG** | — | Only one with normative spec, executable registry, release gate |
| Open Source Freedom | **Superpowers/OMG/OMC/OMX** | — | All MIT; oh-my-openagent is SUL-1.0 (non-commercial only) |
| Codex-Specific | **OMX** | — | Purpose-built with Rust runtime, worktree teams, multi-provider mixing |
| Self-Improvement | **Superpowers** | oh-my-openagent | Skills can author new skills; OpenAgent partially self-develops via Sisyphus |

---

## 7. Production Readiness Ranking

| Rank | Framework | Score | Reasoning |
|---|---|---|---|
| 1 | **OMG v2.3.0** | 9/10 | Production control-plane contract, 290 tests, CI/CD, mutation gates, encrypted state, release surface compiler, host-parity validation, budget governance. The only one with a real governance model. |
| 2 | **Superpowers v5.0.5** | 8/10 | ~100K stars + Anthropic-verified validates massive real-world use. Methodology enforcement works. But no CI and frequent breaking changes are concerning. |
| 3 | **oh-my-claudecode v4.9.0** | 7/10 | Strongest orchestration (7 modes), 7 CI workflows, 4060+ runs. Rapid churn and orphaned process bugs reduce confidence. |
| 4 | **oh-my-openagent v3.12.x** | 6/10 | Technically innovative, massive community. But SUL-1.0 kills commercial use, OpenCode lock-in, 436 open issues, beta stability. |
| 5 | **oh-my-codex v0.11.x** | 5.5/10 | Sound architecture (Rust, worktrees, MCP state) but pre-1.0, Codex-only, single maintainer, smallest ecosystem. |

---

## 8. Recommendation Matrix

### By Use Case

| Use Case | Recommended | Why |
|---|---|---|
| **Enterprise / Production** | **OMG** | Governance, contracts, evidence gates, MIT license, multi-host |
| **Solo Developer / Learning** | **Superpowers** | 1-command install, enforced best practices, massive community |
| **Claude Code Power User** | **OMC** | 7 orchestration modes, tmux teams, magic keywords |
| **OpenCode User (non-commercial)** | **oh-my-openagent** | Hashline edits, LSP, multi-model, but SUL-1.0 license |
| **Codex CLI User** | **OMX** | Purpose-built, Rust runtime, worktree isolation |
| **Multi-host / Vendor-neutral** | **OMG** | Only framework with behavior-parity contracts across 4 hosts |
| **Maximum Community Support** | **Superpowers** | ~100K stars, Anthropic-verified, marketplace ecosystem |

### If You Can Only Pick One

**For production projects: OMG v2.3.0**

1. Only framework with real programmatic governance (mutation gates, proof gates, claim judges, policy engines)
2. Multi-host parity means no vendor lock-in (Claude, Codex, Gemini, Kimi)
3. MIT licensed (no commercial restrictions, unlike oh-my-openagent)
4. 290 test files with parallel execution and coverage reporting
5. Evidence-backed verification is enforced, not optional
6. Absorbs patterns from Superpowers, OMC, and OMX installations
7. Cost tracking and budget governance built in

**Trade-off**: OMG is the most complex to set up and the heaviest to run. For simple solo work, Superpowers is faster to adopt. For Claude Code-specific team orchestration, OMC is more focused.

**For hobby/learning: Superpowers v5.0.5**

1. One-command install, zero configuration
2. The 7-phase workflow teaches disciplined development
3. 233K installs and Anthropic-verified means thoroughly battle-tested
4. Auto-updating skills without manual intervention

---

## Sources

- Local codebase analysis: OMG v2.3.0 (`/Users/cminseo/Documents/scripts/Shell/OMG/`)
- [GitHub - obra/superpowers](https://github.com/obra/superpowers)
- [GitHub - Yeachan-Heo/oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode)
- [GitHub - code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent)
- [GitHub - Yeachan-Heo/oh-my-codex](https://github.com/Yeachan-Heo/oh-my-codex)
- [Superpowers - Anthropic Plugin Page](https://claude.com/plugins/superpowers)
- [ohmyclaudecode.com](https://ohmyclaudecode.com/)
- [ohmyopenagent.com](https://ohmyopenagent.com)
- [oh-my-codex website](https://yeachan-heo.github.io/oh-my-codex-website/)
