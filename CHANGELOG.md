# Changelog

## Unreleased

- wired shipped `safe` preset `PreToolUse` security enforcement so `firewall.py` runs for `Bash` and `secret-guard.py` runs for file reads and edits before the helper hook
- moved raw `env`, interpreter, and permission-changing shell commands from `allow` to `ask` in the shipped `safe` preset
- blocked allowlist overrides for secret and sensitive file denies, sanitized `run_id` and REPL `session_id` values, and added path-containment checks for evidence and REPL state writes
- centralized MCP config writing validation across Claude, Codex, Gemini, and Kimi writers to reject invalid server names and URLs
- added regression coverage for the shipped settings, policy engine, evidence ingest, REPL session persistence, and MCP config writers/providers

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
