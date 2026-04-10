# Changelog

## [3.0.0-rc] - 2026-04-10

### Added

- Provider expansion with confirmed providers and pending stubs
- Anti-distillation domain pack validation
- Governance soft-block enforcement
- Platform compatibility checks

## [2.9.0] - 2026-04-10

### Added

- Phase 3 integration coverage for auto-escalation, trajectory tracking, governance routing, and autoresearch daemon concepts
- Eval-Driven Pipeline with trajectory tracking and regression detection
- Smart Task Handling with auto-classification and model escalation
- `/autoresearch` daemon mode with security envelope and aligned v2.9.0 release surfaces

## [2.7.0] - 2026-04-10

### Added

- Phase 2 integration coverage for wave optimization, escalation, planning context retention, and traceability exports
- Phase 2 release surfaces aligned to v2.7.0 across package metadata, Python packaging, and TypeScript entrypoint
- Phase 2 migration plan for the 2.5.0 → 2.7.0 config upgrade path

## [2.5.0] - 2026-04-07

### Added

- CMMS tier-aware memory routing (Auto/Micro/Ship layers) behind feature flag
- `/pause` command with checkpoint persistence for session state
- `/continue` command with checkpoint restoration and staleness check
- Context durability with freshness score, decay detection, and adaptive reconstruction
- Society of Thought debate integration into planning pipeline (complexity-gated)
- Reliability scoring wired into HUD dashboard
- Governance graph compliance enforcement (advisory mode)
- Advanced handoff retry optimization with budget tracking
- `memory tier-status` CLI inspection command
- Session lifecycle context durability monitoring

## [Phase 2] MemoryStore Plaintext Removal (BREAKING)

### Changed

- `MemoryStore._decrypt_text()` now raises `ValueError` for plaintext entries
- Previously emitted `DeprecationWarning` in Phase 1; plaintext reads are now hard-blocked

### Migration

Run `npx omg memory migrate` to encrypt all existing plaintext entries before upgrading.

<!-- OMG:GENERATED:changelog-v2.3.0 -->

### Governed Release Surface (v2.3.0)

- Canonical release surface compilation
- Dual-channel artifact output (public + enterprise)
- TypeScript rewrite with Bun runtime
- 5-wave orchestration engine
<!-- /OMG:GENERATED:changelog-v2.3.0 -->

## 2.3.0 - 2026-04-05

### OMG v2 — TypeScript Rewrite, Smart Orchestration, Multi-Agent Compatibility

This release merges PRs #129, #130, #131 plus the complete wave 2–5 orchestration engine. 561 files changed, 42,000+ lines added. All 132 version surfaces bumped to v2.3.0.

#### TypeScript Rewrite (Bun Runtime)

- **full rewrite**: complete TypeScript reimplementation with Bun as the canonical runtime
- **type system**: port Python dataclasses to TypeScript interfaces + Zod schemas
- **SQLite state**: Bun SQLite foundation with FTS5 full-text search and atomic IO
- **crypto module**: AES-256-GCM + PBKDF2 + Ed25519 security module in TypeScript
- **config**: settings loader + feature flags + 6 presets
- **CLI**: `bunx omg` CLI with install planner, env doctor, ship, and proof commands

#### Smart Orchestration Engine

- **DAG executor**: DAG-based task execution with dynamic tasks, timeouts, and streaming
- **decision engine**: budget envelopes with multi-dimensional resource tracking
- **team router**: critics + executor pattern for multi-agent coordination
- **exec kernel**: worker watchdog + forge system for reliable execution
- **reflection loops**: self-improving routing with async sub-agent dispatch
- **unified session runtime**: execution modes and HUD system

#### Wave 2 — Protocol & Reliability

- **A2A protocol**: agent-to-agent communication with epistemic tracker
- **deadlock prevention**: reliability calibration suite
- **harness layers 4-5**: context handoff and cross-agent coordination

#### Wave 3 — Governance & Detection

- **Society of Thought**: multi-perspective reasoning framework
- **Governance Graph**: structured policy evaluation
- **Collusion Detection**: anti-coordination failure mechanism
- **Failure Taxonomy**: categorized failure modes for diagnostics

#### Wave 4 — Context Engineering

- **context engine**: compression and pressure management
- **durability checkpoints**: workspace reconstruction protocol
- **context strategy router**: branch evaluation for optimal context allocation
- **metacognitive pipeline**: uncertainty scoring and domain classification

#### Wave 5 — Cross-Frontier Integration

- **cross-frontier integration**: multi-host parity verification
- **parity matrix**: cross-language contract enforcement
- **retention policy**: intelligent context pruning
- **performance tests**: end-to-end integration benchmarks

#### MCP Control Plane

- **omg-control server**: stdio transport + middleware architecture
- **verification tools**: evidence + proof gate tool registration
- **governance tools**: policy + lane-based tool fabric
- **health + scoreboard**: session health monitoring and scoring

#### Security Hardening

- **JWT auth**: rate limiting + HMAC audit trail + threat scoring
- **prompt injection defense**: multi-layer defense engine
- **trust tiers**: defense state + secret guard + credential store
- **firewall**: hard-blocking command screening with policy engine
- **Ed25519 signed manifests**: trust review with cryptographic verification

#### Host Compatibility

- **hook emulation**: cross-host hook behavior normalization
- **compensators**: trailing-off, completeness, deferral, merge-validator, completion-enforcer
- **ASI drift reliability**: reliability calibration for different model behaviors
- **cross-host integration tests**: full parity test suite

#### Provider Adapters

- **Claude + Codex + Gemini + Kimi + OpenCode**: unified provider adapters
- **git tools**: integrated version control operations
- **browser + LSP + web search**: config utilities for extended tool support

#### Improvements (PR #129)

- **README 전면 개편**: killer features, comparison table, architecture diagram
- **MutationGate hard-block**: real mutation blocking (not just advisory)
- **보안 강화**: strengthened default security posture

#### Code Quality Hardening (PR #131)

- **error handling**: comprehensive error handling improvements
- **performance**: optimized hot paths
- **tests**: expanded test coverage
- **docs**: documentation accuracy fixes

#### Inherited from v2.2.12

- All changes from PRs #116–#121 (username migration, AI enhancement, security tightening, 18 agents, test coverage, hook hardening)

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
