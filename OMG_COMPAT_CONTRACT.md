---
title: OMG Production Control Plane
version: 2.0.9
canonical_hosts:
  - claude
  - codex
  - gemini
  - kimi
status: active
---

# OMG Production Control Plane

`OMG_COMPAT_CONTRACT.md` is the normative human-readable contract for OMG capability bundles. Machine-readable manifests in `registry/bundles/` are executable inputs and must remain version-locked to this document.

## provider_tiers

OMG defines four canonical hosts and their host-rule contracts.

- `claude`: requires `compilation_targets`, `hooks`, `subagents`, and `skills`.
- `codex`: requires `compilation_targets`, `skills`, `agents_fragments`, `rules`, and `automations`.
- `gemini`: requires `compilation_targets`, `mcp`, `skills`, and `automations`.
- `kimi`: requires `compilation_targets`, `mcp`, `skills`, and `automations`.

Gemini and Kimi are canonical hosts for contract validation and policy declaration. Their contracts do not require Claude/Codex hook semantics.

## metadata

Every bundle must declare `id`, `kind`, `version`, `title`, `description`, `hosts`, and `assets`.

## invocation_policy

Every bundle must declare whether it is user invocable, model invocable, and whether implicit invocation is allowed. Production bundles default to explicit invocation only.

## tool_policy

Every bundle must declare `side_effect_level` and host-specific allowed tools. Production policy protects `.omg/`, `.agents/`, `.codex/`, and `.claude/` as control-plane state.

## lifecycle_hooks

Canonical OMG events:

- `SessionStart`
- `SessionEnd`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `Stop`
- `PreCompact`
- `ConfigChange`
- `WorktreeCreate`
- `WorktreeRemove`
- `SubagentStart`
- `SubagentStop`
- `TaskCompleted`

Hosts compile native events where available and emulate the rest with OMG runtime wrappers.

## mcp_contract

Bundles may declare MCP servers, prompts, resources, and server instructions. `omg-control` is the primary stdio server. HTTP control-plane exposure is loopback-only and not a production launch dependency.

## lsp_contract

LSP packs declare supported languages, diagnostics expectations, and evidence outputs for post-edit checks.

## evidence_outputs

Bundles declare reproducible evidence artifacts under `.omg/evidence/` or `.omg/state/`. Release-ready bundles must emit deterministic outputs suitable for CI drift checks.

## execution_contract

Supported execution modes:

- `embedded`
- `local_supervisor`
- `automation`
- `ephemeral_worktree`

`local_supervisor` means a same-machine orchestrator driving Claude and Codex workers through local CLI or stdio MCP integration. Remote multi-tenant control planes are out of scope for this version.

## host_compilation_rules

Claude outputs compile to:

- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `.mcp.json`
- generated hook configuration consumed by `settings.json`

Codex outputs compile to:

- `.agents/skills/omg/<bundle>/SKILL.md`
- `.agents/skills/omg/<bundle>/openai.yaml`
- generated Codex MCP and rule fragments under `.agents/skills/omg/`

## roadmap_extensions

The contract reserves compilation anchors for:

- `omg.skill-compiler`
- `omg.hook-governor`
- `omg.mcp-fabric`
- `omg.lsp-pack`
- `omg.secure-worktree-pipeline`
