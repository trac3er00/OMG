# Learnings — omg-v2-2-3-clean-strong-release

## [2026-03-14] Session Init
- Main worktree: /Users/cminseo/Documents/scripts/Shell/OMG
- Current HEAD: eebd69478596eaa243f4f06ce2d6ac4391e19be0
- Branch: main
- Key runtime files confirmed present: release_surfaces.py, context_limits.py, evidence_requirements.py, contract_compiler.py, host_parity.py, merge_writer.py, compliance_governor.py, proof_gate.py, claim_judge.py, guide_assert.py, background_verification.py, canonical_surface.py, mutation_gate.py
- Key scripts confirmed: sync-release-identity.py, validate-release-identity.py, omg.py
- NOTE: done_when_required false positive blocks mkdir/Write MCP — use filesystem MCP instead

## [2026-03-14] Release identity enforcement hardening
- Added .gemini/settings.json and .kimi/mcp.json to AUTHORED_SURFACES with json_key_path selectors for _omg._version and _omg.generated.contract_version (source_only=False).
- Required workflow_dispatch input FORBID_VERSION is now declared in omg-release-readiness, omg-compat-gate, and publish-npm workflows.
- All workflow validate steps now pass --forbid-version explicitly via ${{ inputs.FORBID_VERSION }} instead of shell fallback expansion.
- Added a validator unit test proving stale Gemini surface values (2.2.2) are blocked when canonical is 2.2.3.
- Captured validation and edge-case evidence under .sisyphus/evidence/task-1-release-identity*.txt.

## [2026-03-14] Runtime hardening for context + done_when
- Model resolution now prioritizes hook payload model identifiers over stale environment model variables, so host/model switches recalculate compaction thresholds immediately.
- Context pressure accounting now separates units: tool calls are counted independently, while high-pressure gating is token-estimate versus token-threshold.
- Bash mutation detection now avoids false positives for read-only commands (`python -V`, `git status`, `gh pr view`, quoted literals, and `tee /dev/null`) while still blocking real mutations (including `bash -lc "touch ..."`).
- `verify_done_when` now records declaration state separately from completion state (`done_when_declared` vs `done_when_completed`) without adding free-text completion evaluation.
- Added regression tests for model-switch threshold recalculation and read-only/mutating Bash edge cases across mutation gate and tool plan gate.
- Captured verification evidence in `.sisyphus/evidence/task-4-runtime-hardening.txt` and `.sisyphus/evidence/task-4-runtime-hardening-error.txt`.

## [2026-03-14] Flagship GitHub PR reviewer bot foundation
- Added GitHub App auth in `runtime/github_integration.py` with RSA JWT signing, installation-token exchange over `requests`, token caching, rate-limit retry, and machine-readable failure codes.
- Added SHA-scoped review lifecycle contract in `runtime/github_review_contract.py` and evidence-only markdown + inline batching formatter in `runtime/github_review_formatter.py`.
- Added orchestrator in `runtime/github_review_bot.py` that posts review + check-run per head SHA, enforces idempotency, and dismisses stale approvals on `pull_request.synchronize`.
- Added mocked unit/e2e coverage for token flow, retry/missing-credential failures, SHA idempotency, stale approval dismissal, missing artifact safe-fail, and full mocked PR flow.
- Captured proof outputs in `.sisyphus/evidence/task-2-pr-reviewer-bot.txt` and `.sisyphus/evidence/task-2-pr-reviewer-bot-error.txt`.

## [2026-03-14] GitHub gates rework for trusted bot handoff
- Added `concurrency` guards (`${{ github.workflow }}-${{ github.ref }}` with cancel-in-progress) to compat, release-readiness, and publish workflows.
- Split compat PR path into untrusted `pr-analyze` (no write-capable credentials) and trusted `post-review` (GitHub App secrets + base-SHA checkout only) with artifact handoff between lanes.
- Added `scripts/github_review_helpers.py` to build PR/release reviewer handoff payloads from stored artifacts, enforce fast blockers, and post reviews via `GitHubReviewBot`.
- Added workflow contract tests in `tests/scripts/test_github_workflows.py` for concurrency, fork-safety, trusted-lane checkout rules, artifact reuse, and helper behavior.
- Captured evidence in `.sisyphus/evidence/task-3-github-gates.txt` and `.sisyphus/evidence/task-3-github-gates-error.txt`.
