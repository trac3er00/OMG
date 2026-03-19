# OMG Commands

OMG exposes a launcher-first front door and keeps the rest of the surface available as advanced plugins.

## Launcher-First Install

> **Prerequisites**: macOS or Linux, Node >=18, Python >=3.10

```bash
npx omg env doctor
npx omg install --plan
npx omg install --apply
npx omg ship
```

Local package-manager installs only link `omg` into `node_modules/.bin/`; configuration changes still require an explicit `npx omg install --apply`.

## Native Plugin Entry Points

| Command | Description |
|---------|-------------|
| `/OMG:ship` | Ship — Idea to Evidence to PR |
| `/OMG:browser` | Canonical browser automation and verification surface |

## Core Commands

| Command | Description |
|---------|-------------|
| `/OMG:init` | Initialize project or domain |
| `/OMG:escalate` | Route to Codex, Gemini, or CCG |
| `/OMG:teams` | Team routing for internal OMG execution |
| `/OMG:ccg` | Tri-track synthesis |
| `/OMG:security-check` | Canonical security pipeline |
| `/OMG:api-twin` | Contract replay and fixture-based API simulation |
| `/OMG:preflight` | Structured route selection and evidence planning |
| `/OMG:browser` | Browser automation and verification powered by the upstream Playwright CLI |
| `/OMG:compat` | Legacy compatibility routing |
| `/OMG:health-check` | Verify setup and tool integration |
| `/OMG:mode` | Set cognitive mode for the session |

## Advanced Commands

| Command | Category | Description |
|---------|----------|-------------|
| `/OMG:deep-plan` | Planning | Strategic planning with domain awareness (compatibility path to `plan-council`) |
| `/OMG:learn` | Knowledge | Convert patterns into OMG-native instincts and skills |
| `/OMG:code-review` | Quality | Deep review flow |
| `/OMG:ship` | Delivery | Idea to evidence to release |
| `/OMG:handoff` | Collaboration | Session transfer and continuity |
| `/OMG:maintainer` | OSS | Open-source maintainer workflows |
| `/OMG:sequential-thinking` | Thinking | Structured multi-step reasoning |
| `/OMG:ralph-start` | Automation | Start Ralph autonomous loop |
| `/OMG:ralph-stop` | Automation | Stop Ralph autonomous loop |

## Plugin Layout

```text
plugins/
  core/
    commands/
    plugin.json
  advanced/
    commands/
    plugin.json
```

## Adoption Notes

Restricted environments / air-gapped fallback: `/OMG:setup` and `OMG-setup.sh` remain available when launcher-first install cannot mutate host configuration directly. `compat` remains focused on legacy skill routing.

`/OMG:playwright` remains available as a compatibility alias to `/OMG:browser`.

## Public Docs

- Install guides live in [docs/install/claude-code.md](../docs/install/claude-code.md) and [docs/install/codex.md](../docs/install/codex.md).
- Proof surface lives in [docs/proof.md](../docs/proof.md).
- Quick reference lives in [QUICK-REFERENCE.md](../QUICK-REFERENCE.md).
- Install verification lives in [INSTALL-VERIFICATION-INDEX.md](../INSTALL-VERIFICATION-INDEX.md).
