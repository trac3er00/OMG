# OMG Browser Command Design

**Date:** 2026-03-08

**Status:** Approved

**Decision:** Canonical `/OMG:browser`, compatibility alias `/OMG:playwright`

## Goal

Add an OMG-owned browser automation and browser-verification surface that works across all OMG-supported hosts by wrapping upstream `playwright-cli` instead of introducing a new OMG browser MCP.

## Why This Direction

- Microsoft now positions `playwright-cli` as a better fit than `playwright-mcp` for coding-agent workflows that already have command and skill surfaces.
- OMG already treats `omg-control` as the canonical MCP surface and keeps host-native MCP wiring narrow.
- Browser execution in this repo already has proof and trust plumbing through [`runtime/playwright_pack.py`](/Users/cminseo/Documents/scripts/Shell/OMG/runtime/playwright_pack.py), [`runtime/proof_gate.py`](/Users/cminseo/Documents/scripts/Shell/OMG/runtime/proof_gate.py), and the browser trust tier.
- A thin OMG wrapper around upstream `playwright-cli` reduces maintenance and keeps browser behavior portable across Claude, Codex, Gemini, and Kimi.

## Public Surface

- Add `/OMG:browser` as the canonical command.
- Add `/OMG:playwright` as a compatibility alias that resolves to the same runtime path.
- Public docs should describe the feature as browser automation and browser verification, not as a new MCP surface.
- Claude users access it via `/OMG:*` commands.
- Non-Claude hosts continue to consume the capability through OMG’s generated packs, docs, and install flow rather than host-native slash commands.

## Execution Model

- OMG owns the command contract, prompts, failure handling, and artifact normalization.
- Upstream `playwright-cli` owns browser execution.
- OMG should add a thin adapter layer that:
  - detects whether the upstream CLI is installed
  - verifies that browser assets are present
  - runs upstream commands with stable OMG defaults
  - copies or summarizes screenshots, traces, and result metadata into `.omg/evidence/`
- The adapter should integrate with the existing browser trust tier and proof-chain expectations rather than bypassing them.

## Install Story

- Browser support is an optional OMG capability, not a required base dependency.
- `OMG-setup.sh` should support an opt-in browser addon path that installs or configures upstream `playwright-cli` and its skills once per machine.
- Setup docs for Claude, Codex, Gemini, and Kimi should all reference the same OMG-managed browser capability because the runtime is host-agnostic.
- The base install should remain lightweight when the user does not opt in.

## Host Model

- Claude: canonical `/OMG:browser` and `/OMG:playwright` slash commands.
- Codex, Gemini, Kimi: no fake slash-command mirroring; instead, the OMG packs and docs should describe the same browser capability and its local verification flow.
- No new host-native MCP dependency is required for browser execution in v1.

## Failure Handling

- Missing upstream CLI should produce a concrete remediation message with the exact install command.
- Missing browser binaries should produce a concrete remediation message with the exact browser-install command.
- Unsupported runtime situations should fail before execution, not after partial artifact creation.
- Raw upstream subprocess output should be normalized into OMG-style summaries.

## Evidence and Proof

- Browser runs should emit artifacts under `.omg/evidence/`.
- Existing proof-chain surfaces should stay authoritative:
  - trace linkage
  - screenshot paths
  - browser evidence JSON
  - trust-tier metadata
- If upstream output shape changes, the OMG adapter should absorb that drift and keep the proof contract stable.

## Repo-Level Changes

- Command surface:
  - create [`commands/OMG:browser.md`](/Users/cminseo/Documents/scripts/Shell/OMG/commands/OMG:browser.md)
  - create [`commands/OMG:playwright.md`](/Users/cminseo/Documents/scripts/Shell/OMG/commands/OMG:playwright.md)
  - register the new command in [`plugins/core/plugin.json`](/Users/cminseo/Documents/scripts/Shell/OMG/plugins/core/plugin.json)
- Runtime:
  - add an OMG browser adapter module under `runtime/`
  - integrate with existing browser evidence code instead of replacing it
- Setup/docs:
  - update [`OMG-setup.sh`](/Users/cminseo/Documents/scripts/Shell/OMG/OMG-setup.sh)
  - update install docs and README
- Tests:
  - command surface and alias coverage
  - install/optional-addon coverage
  - runtime adapter and evidence-path coverage

## Non-Goals

- No OMG-owned replacement for Playwright.
- No new browser MCP server in v1.
- No host-specific parallel implementations.
- No attempt to expose Claude slash commands directly inside Codex, Gemini, or Kimi.

## Recommended Rollout

1. Add docs and command-registration scaffolding.
2. Add adapter and failing runtime tests.
3. Add optional setup/install flow.
4. Wire browser proof artifacts.
5. Update public docs and verification guidance.
