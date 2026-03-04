# OMG Commands

OMG (Oh My OpenCode Alternative) provides two tiers of commands:

## Core Commands (`commands/`)

Essential functionality available in all OMG installations:

| Command | Description |
|---------|-------------|
| `/OMG:init` | Initialize project or domain |
| `/OMG:escalate` | Route to Codex/Gemini/CCG |
| `/OMG:teams` | Team routing (standalone) |
| `/OMG:ccg` | Tri-track synthesis (Claude+Codex+Gemini) |
| `/OMG:crazy` | Parallel multi-agent orchestration |
| `/OMG:compat` | Legacy compatibility dispatcher |
| `/OMG:health-check` | Verify setup and tools |
| `/OMG:mode` | Set cognitive mode |

## Advanced Commands (`plugins/advanced/`)

Extended functionality for specialized workflows:

| Command | Category | Description |
|---------|----------|-------------|
| `/OMG:deep-plan` | Planning | Strategic planning with domain awareness |
| `/OMG:learn` | Knowledge | Create skills from patterns |
| `/OMG:code-review` | Quality | Deep code review |
| `/OMG:security-review` | Security | Security vulnerability scanning |
| `/OMG:ship` | Delivery | Ship pipeline (idea → PR) |
| `/OMG:handoff` | Collaboration | Session transfer |
| `/OMG:maintainer` | OSS | Open-source maintainer tools |
| `/OMG:sequential-thinking` | Thinking | Structured reasoning |
| `/OMG:ralph-start` | Automation | Start Ralph loop |
| `/OMG:ralph-stop` | Automation | Stop Ralph loop |

## Plugin Architecture

Commands are organized as plugins:

```
plugins/
├── core/           # Essential commands
│   ├── commands/   # Command definitions
│   └── plugin.json # Plugin manifest
└── advanced/       # Extended commands
    ├── commands/
    └── plugin.json
```

### Using Advanced Commands

Advanced commands work the same as core commands:

```
/OMG:deep-plan implement OAuth2 flow
/OMG:learn from this session
/OMG:code-review src/auth.ts
```

### Creating Custom Plugins

1. Create `plugins/my-plugin/plugin.json`
2. Add commands to `plugins/my-plugin/commands/`
3. OMG auto-discovers plugins on startup

See `plugins/advanced/` for examples.

## Migration from Legacy Plugins

Advanced commands are OMG-native equivalents of legacy plugin capabilities:

| Legacy Plugin | OMG Advanced |
|-------------|--------------|
| `writing-plans` | `/OMG:deep-plan` |
| `learner` | `/OMG:learn` |
| `requesting-code-review` | `/OMG:code-review` |
| `security-review` | `/OMG:security-review` |
| `finishing-a-development-branch` | `/OMG:ship` |
| `handoff` | `/OMG:handoff` |

OMG advanced commands are designed for OMG standalone mode without requiring external plugins.
