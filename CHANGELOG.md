# Changelog

## Unreleased

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
