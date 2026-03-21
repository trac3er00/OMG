# Changelog

## 2.3.0 - 2026-03-20

### v2.3.0 — Performance, Consolidation, Security, and Multi-Agent Orchestration

#### Performance Foundation
- **State file cache**: mtime-based cache with 100ms TTL in `_common.py` — cached reads at 0.002ms/call
- **Lazy imports**: deferred `re`, `hashlib`, `datetime` in prompt-enhancer.py; lazy module loading in budget_governor.py
- **Fast-path optimization**: zero-injection threshold raised from 10 to 15 words with set-based matching (no regex on fast path)
- **Hook consolidation**: pre-tool-all.py and post-tool-all.py dispatchers reduce subprocess overhead

#### Command Consolidation (20 → 12 active commands)
- `/OMG:validate` absorbs doctor, health-check, diagnose-plugins
- `/OMG:init` absorbs setup wizard
- `/OMG:session` absorbs session-branch, session-fork, session-merge
- `/OMG:ralph` absorbs ralph-start, ralph-stop
- `/OMG:crazy` absorbs ccg, teams (as modes: ccg, team, swarm, pipeline)
- `/OMG:stats` absorbs cost tracking
- Removed: playwright (alias), compat (legacy), theme (non-critical)
- All deprecated commands print redirect messages

#### Security
- **SSRF prevention**: firewall blocks curl/wget to internal/private IPs (127.x, 10.x, 192.168.x, metadata endpoints)
- **Path traversal enforcement**: secret-guard validates resolved paths stay within project boundaries
- **HMAC integrity**: defense state files protected against tampering with machine-specific HMAC
- **Structured error output**: `PolicyDecision.to_structured_error()` with actionable suggestions

#### Unified /OMG:issue
- Parallel sub-agent orchestrator with 6 agents: red-team, dep-audit, secret-scan, env-scan, privacy-audit, leak-detective
- Finding aggregator: fingerprint-based deduplication, severity ranking, trust scores
- SARIF 2.1 output format for CI/CD integration

#### Setup Simplification
- `npx omg quickstart` one-liner with tiered install (Level 1/2/3)
- Progress indicators in OMG-setup.sh (visual progress bar)
- Enhanced pre-flight: 5 dependency checks (Python, venv, git, host dir, disk space)

#### Deep-Plan v2
- Item classification (NEEDED/NICE-TO-HAVE/NOT-NEEDED)
- Per-plan folder structure (.omg/plans/<id>/)
- File-overlap analysis and merge conflict risk flagging
- Multi-model planning with Codex validation and Gemini UX review

#### New Commands
- `/OMG:start-work` — Plan-driven implementation with session strategy
- `/OMG:mode tdd` — RED-GREEN-REFACTOR cycle enforcement

#### Infrastructure
- SQLite ledger (runtime/sqlite_ledger.py) as JSONL replacement
- MCP overlap detection (runtime/mcp_dedup.py)
- Plugin cohesion checker (runtime/plugin_cohesion.py)
- Git-backed agent store (runtime/agent_store.py)
- State file rotation (runtime/state_rotation.py)
- Multi-host E2E test suite with CI matrix
- HUD improvements: hide-when-ok, adaptive suppression, model-aware context %

#### Documentation
- Getting Started guide (zero to working in 5 min)
- Troubleshooting guide (OS-specific)
- Command reference with examples
- README install decision tree

<!-- OMG:GENERATED:changelog-v2.2.12 -->
### Governed Release Surface (v2.2.12)

- Canonical release surface compilation
- Dual-channel artifact output (public + enterprise)
- Idempotent generated-section markers in docs
<!-- /OMG:GENERATED:changelog-v2.2.12 -->

## 2.2.12 - 2026-03-20

### Consolidated Feature Release — AI Enhancement, Security Hardening, Agent Expansion, Test Coverage

This release merges 6 PRs (#116–#121) into a single governed release. All surfaces bumped to v2.2.12.

#### Identity — Username Migration (#116)
- **username rename**: update 51 files referencing old GitHub username `trac3er00` → `trac3r00`
- Fixes CLA allowlist mismatch, plugin URLs, docs, registry, and tests

#### AI Enhancement — CoT, Model Hints, Tool Discovery (#117)
- **CoT preamble injection**: inject chain-of-thought preamble for complex tasks (complexity >= 4)
- **model parameter hints**: opus for HIGH complexity, sonnet for MEDIUM
- **metaprompt auto-trigger**: auto-trigger when Codex detected at runtime
- **semantic tool discovery**: 22-tool keyword catalog for context-aware tool selection
- **prompt compiler**: outcome-tracked template selection with budget awareness

#### Security — Permission Tightening (#118)
- **sensitive command migration**: move 17 sensitive command patterns from `allow` to `ask` in settings.json
- Strengthens default security posture without breaking existing workflows

#### Agents — 18 New Specialized Definitions (#119)
- **new agents**: accessibility-auditor, api-tester, code-archeologist, concurrency-expert, config-manager, data-engineer, debugger, dependency-analyst, devops-engineer, docs-writer, error-handler, log-analyst, migration-specialist, ml-engineer, performance-engineer, prototype-builder, refactor-agent, release-engineer
- All agents include frontmatter with name, description, model, and tools for `agent_selector.py`

#### Test Coverage — Deep Plan and Runtime (#120)
- **16 new test files** covering agents, hooks, runtime, and CLI
- ~6,500 lines of test coverage across context engine, evidence narrator, skill foundry, task routing, coordinator state, dispatch strategy, and more

#### Hooks — Cross-Hook Wiring and Reentry Guard (#121)
- **reentry guard**: prevent concurrent hook execution with file-based locking
- **circuit-breaker wiring**: wire circuit-breaker to stop-block loop detection
- **ledger rotation**: cap tool-ledger.jsonl at 10K lines
- **verification accuracy**: `check_verification()` uses current-turn commands from stop payload
- **memory/planning exclusion**: memory and planning file writes excluded from source-write detection

#### Inherited from v2.2.11

##### CI/CD — Migrate to Cubic AI Review Agents
- **cubic AI migration**: replace all legacy GitHub Actions review workflows with 5 Cubic AI custom agents
- **CLA workflow**: add CLA Assistant Lite for contributor license agreement signing
- **GitGuardian**: add automated secret scanning on push and pull request events

##### Runtime — Release Artifact Audit Gate
- **release artifact audit**: new `runtime/release_artifact_audit.py` — validates version parity, file completeness, and security properties
- **path traversal fix**: replace `startswith()` with `is_relative_to()` to close traversal bypass
- **contract snapshots**: regenerate both contract snapshots with `host_surfaces` field

##### Documentation — Launcher-First and Proof Framing
- **launcher-first docs**: make public docs and install guides launcher-first
- **version regex anchors**: add word-boundary anchors to prevent prefix matches

## 2.2.9 - 2026-03-18

### Version Alignment and Documentation Accuracy

- **version alignment**: bump all surfaces to match v2.2.9 tag
- **documentation accuracy**: replace false postinstall claims; npm postinstall runs `omg install --plan` as a preview and makes no mutations
- **install flow rewrite**: canonical front door is now `npx omg env doctor` -> `npx omg install --plan` -> `npx omg install --apply` -> `npx omg ship`
- **legacy demotion**: `/OMG:setup` -> `/OMG:crazy` moved to legacy footnotes; `OMG-setup.sh` demoted to compatibility path
- **docs compiler expansion**: add generators for install intro, why OMG, proof quickstart, quick-reference hosts, and verification index targets
- **kill banned copy**: remove the stale install-language phrase from tracked markdown surfaces

## 2.2.8 - 2026-03-18

### Version Alignment and Documentation Accuracy

- **version bump**: align package.json, all authored surfaces, and release artifacts with the v2.2.8 tag
- **doc accuracy**: replace false postinstall claims (plan-only, not register/wire), fix bare `omg` examples to use `npx omg`
- **prerequisite banner**: document Node >=18, Python 3.10+, macOS/Linux requirement prominently
- **install guide cleanup**: remove duplicate Fast Path sections, expand QUICK-REFERENCE command surface
- **stale version refs**: update opencode.md from v2.2.5, INSTALL-VERIFICATION-INDEX from 2.2.7

## 2.2.7 - 2026-03-15

### Governed Execution Engine Milestone

- **production preset**: new `production` preset enables all governed flags — use `--preset=production` with `OMG-setup.sh` or `bunx @trac3r/oh-my-god`
- **bunx install path**: `bunx @trac3r/oh-my-god` works alongside `npm install`
- **terms_guard**: real enforcement blocks promotional cross-model sharing, hidden identity switching, undisclosed third-party data sharing
- **six governed agents**: `architect-planner`, `explorer-indexer`, `implementer`, `security-reviewer`, `verifier`, `causal-tracer` compiled into Claude host artifacts; no `bypassPermissions` on any
- **method compiler**: `contract compile --method` emits signed seven-phase methodology artifacts
- **context compiler**: `context compile` emits bounded provenance-only packets for Claude, Codex, Gemini, and Kimi
- **provider parity eval**: `provider-parity-eval --task task.json --mode recorded` evaluates all canonical hosts and emits a structured report
- **PR risk engine**: structured risk classification by changed area; required gates and bundles exposed in PR review output
- **governance hotfixes**: `verify_done_when({})` returns `ok`, `git tag -l` not classified as mutation, test-validator false positives eliminated
- canonical hosts: `claude`, `codex`, `gemini`, `kimi`; OpenCode remains compatibility-only

## 2.2.3 - 2026-03-11

- fixed `/OMG:deep-plan` 404 by adding missing root compatibility stub routing to canonical plan-council bundle
- added manifest-driven release readiness gate that audits plugin command source paths against manifests and fails fast on missing files
- removed hard-coded artifact constant; advanced plugin artifacts now derived dynamically from `plugins/advanced/plugin.json`
- purged all `2.1.1` version residue from scripts, docs, CI workflows, and tests; tightened identity validation to strict exit-code 0
- added proof-backed compliance governor as single precedence authority over tool-plan gating, claim-judge verdicts, and artifact trust checks
- added deterministic forge run contracts with explicit seed derivation and replay validation
- shipped local-first agentic storage foundation with SQLite/FTS5 full-text search and adjacency-table lineage
- added HMAC-SHA256 offline signed artifact attestation; release promotion gate now blocks unsigned artifacts
- added sandboxed Forge runner with explicit time, cost, GPU, and network budget enforcement per run
- shipped live Axolotl adapter with SFT/GRPO/GDPO modes, bounded hyperparameter search, and LoRA double-stacking guards
- added live simulator backends for PyBullet, Gazebo, and Isaac Gym with CPU-only mock for CI environments
- replaced simulated Forge pipeline outcomes with live evidence; `simulated_metric` fully removed as success criterion
- added buffet preset as canonical configuration with single source of truth across setup, runtime, and config; includes `NOTEBOOKLM` and `COUNCIL_ROUTING` flags
- added bounded session health auto-actions (pause, reflect, warn, require-review) with explicit evidence persistence
- extended host-parity compiler with claim-judge and compliance governor in release audit; Gemini and Kimi added as canonical hosts
- expanded 5 evidence profiles (browser-flow, forge-cybersecurity, interop-diagnosis, install-validation, buffet) with concrete non-placeholder data

## 2.1.5 - 2026-03-09

- shipped Forge v0.3 as the flagship feature
- added adapter contract layer (axolotl, pybullet, gazebo, isaac_gym)
- expanded domain-pack coverage for all 5 domains (vision, robotics, algorithms, health, cybersecurity)
- introduced domain-specific CLI commands
- delivered release-grade evidence bundles with artifact contracts
- normalized run identity and domain registry

## 2.1.4 - 2026-03-09

- bump authored release identity to 2.1.4 across all 42 authored surfaces
- refresh compat contract snapshot

## [historical] 2.1.x - 2026-03-08

- shipped strict TDD-or-die enforcement: locked-tests-first mutation lifecycle with hard gate via `OMG_TDD_GATE_STRICT`, stop-dispatcher lock enforcement, waiver evidence requirement, and release-blocking proof chain
- delivered granular per-interaction undo/rollback: `restore_shadow_entry` in shadow manager, rollback manifest schema with compensating actions for reversible external side effects, and `omg undo` CLI wired end-to-end
- added live session health monitoring and HUD freshness: `compute_session_health()` and `DefenseState.update()` called after real mutations and verifications, 5-minute HUD staleness threshold with `[STALE]` badge, and MCP `get_session_health` tool with `/session_health` control-plane route
- persisted and enforced defense-council verdicts: `run_critics()` result no longer silently discarded, council findings flow into routing, tool-plan gate, claim judge, and release blocking; new `evidence_completeness` critic added
- hardened Forge starter: strict domain/specialist validation, proof-backed starter evidence, labs-only release proof integration
- added canonical run-scoped release coordinator (`runtime/release_run_coordinator.py`) as single authority for `run_id` lifecycle across verification, journaling, health, council, and rollback artifacts
- expanded runtime state contracts for `session_health`, `council_verdicts`, `rollback_manifest`, and `release_run` as first-class versioned schemas
- all new hard gates are feature-flagged permissive by default (`OMG_TDD_GATE_STRICT=1`, `OMG_RUN_COORDINATOR_STRICT=1`, `OMG_PROOF_CHAIN_STRICT=1`)

## 2.1.0 - 2026-03-08

- promoted the execution-primitives and browser-surface wave into the v2.1.0 release train
- aligned package, plugin, HUD, contract, snapshot, and compiled manifest identity on v2.1.0
- regenerated public and enterprise release manifests and bundles for the new canonical version
- expanded version-drift coverage to include committed release manifests and the HUD fallback path
- restored public-release readiness by removing internal planning docs from the branch and installing runtime dependencies in CI workflows

## 2.0.9 - 2026-03-08

- added scan-first evidence query layer for read-only trust artifact lookup
- extended claim-judge and test-intent-lock with query-backed workflows and file-backed lock state
- exposed claim-judge and test-intent-lock through control-plane service, HTTP routes, and MCP tools
- added deterministic repro-pack manifest assembly from existing evidence, trace, eval, and lineage artifacts
- added optional playwright evidence adapter for proof-chain-friendly browser artifact summarization
- added bounded verification-loop policy helpers with no execution side effects
- integrated new sibling artifacts into proof chain, evidence ingest, and release readiness

## 2.0.8 - 2026-03-07

- restored plan-council, claim-judge, test-intent-lock, and proof-gate to all required surfaces
- clarified Gemini and Kimi as compatibility providers vs canonical hosts
- aligned /OMG:deep-plan as compatibility path to plan-council
- added bundle promotion parity drift blockers to release gate

## 2.0.7 - 2026-03-07

- canonicalized v2.0.7 release identity across all source, tests, and generated security artifact metadata
- updated README.md heading to `# OMG` (removed version from H1 permanently) and removed `- Version: 2.0.5` line from brand metadata block
- refactored identity tests to derive expected version from CANONICAL_VERSION instead of hardcoding values
- extended release-readiness/version-drift coverage to newly canonicalized locations and updated contract_compiler.py to skip README H1 version check

## 2.0.5 - 2026-03-07

- expanded release identity and version-drift gate across full public surface (README.md, package.json, pyproject.toml, settings.json, .claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugins/core/plugin.json, plugins/advanced/plugin.json, CHANGELOG.md)
- fixed plugins/advanced/plugin.json version drift from 1.0.5 to 2.0.5
- added canonical version source of truth in runtime/adoption.py with comprehensive drift detection

## 2.0.4 - 2026-03-07

- shipped the OMG production control plane contract, executable bundle registry, host compiler, and dual-channel public and enterprise release bundles
- generated Codex skill packs and Claude release artifacts from the canonical contract, and added CI release-readiness coverage for validation, compile, standalone, and public-readiness gates
- extended the stdio `omg-control` MCP with prompts, resources, and server instructions, and upgraded subagent execution to record real worker evidence with secure worktree handling
- hardened the shipped `safe` preset so `firewall.py` runs before Bash tools, `secret-guard.py` runs before file mutations, and raw env or interpreter surfaces require approval
- fixed portable runtime provisioning to include `plugins/`, prevented worker command prompt placeholders from breaking argv boundaries, and corrected `omg_natives` import-path shadowing of stdlib modules

## 2.0.3 - 2026-03-06

- removed OpenCode runtime, setup wiring, docs, and tests from the supported OMG host surface
- merged the remaining security and trust-review hardening work into `main` and cleaned up the finished `codex/*` branches
- published the post-merge patch release after the `v2.0.2` release target became immutable

## 2.0.2 - 2026-03-06

- cleaned the repo for public launch by removing internal planning docs and stale private references
- added a public-readiness checker plus CI enforcement for docs, links, and community templates
- rewrote the public docs funnel around install, `/OMG:setup`, `/OMG:crazy`, proof, and contribution guidance

## 2.0.1 - 2026-03-06

- standardized OMG public identity across docs, package metadata, plugin metadata, and CLI surfaces
- added native adoption flow through `OMG-setup.sh` and `/OMG:setup` with `OMG-only` and `coexist` modes
- added public-readiness hygiene checks and contributor-facing repo docs
- rewrote the public docs funnel around host install, `/OMG:setup`, `/OMG:crazy`, and proof-backed verification
