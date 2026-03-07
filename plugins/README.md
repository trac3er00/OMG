# OMG Commands

OMG exposes a small native front door and keeps the rest of the surface available as advanced plugins.

## Native Entry Points

| Command | Description |
|---------|-------------|
| `/OMG:setup` | Native setup and adoption flow for supported hosts |
| `/OMG:crazy` | Default OMG orchestration flow |

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
| `/OMG:compat` | Legacy compatibility routing |
| `/OMG:health-check` | Verify setup and tool integration |
| `/OMG:mode` | Set cognitive mode for the session |

## Advanced Commands

| Command | Category | Description |
|---------|----------|-------------|
| `/OMG:deep-plan` | Planning | Strategic planning with domain awareness |
| `/OMG:learn` | Knowledge | Convert patterns into OMG-native instincts and skills |
| `/OMG:code-review` | Quality | Deep review flow |
| `/OMG:ship` | Delivery | Idea to evidence to release |
| `/OMG:handoff` | Collaboration | Session transfer and continuity |

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

Public migration commands are intentionally avoided. OMG uses `/OMG:setup` and `OMG-setup.sh` to detect and adopt older ecosystems internally, while `compat` remains focused on legacy skill routing.

## Public Docs

- Install guides live in [docs/install/claude-code.md](../docs/install/claude-code.md) and [docs/install/codex.md](../docs/install/codex.md).
- Proof surface lives in [docs/proof.md](../docs/proof.md).
