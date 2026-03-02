# OAL Commands

OAL (Oh My OpenCode Alternative) provides two tiers of commands:

## Core Commands (`commands/`)

Essential functionality available in all OAL installations:

| Command | Description |
|---------|-------------|
| `/OAL:init` | Initialize project or domain |
| `/OAL:escalate` | Route to Codex/Gemini/CCG |
| `/OAL:teams` | Team routing (standalone) |
| `/OAL:ccg` | Tri-track synthesis (Claude+Codex+Gemini) |
| `/OAL:crazy` | Sequential multi-agent orchestration |
| `/OAL:compat` | Legacy compatibility dispatcher |
| `/OAL:health-check` | Verify setup and tools |
| `/OAL:mode` | Set cognitive mode |

## Advanced Commands (`plugins/advanced/`)

Extended functionality for specialized workflows:

| Command | Category | Description |
|---------|----------|-------------|
| `/OAL:deep-plan` | Planning | Strategic planning with domain awareness |
| `/OAL:learn` | Knowledge | Create skills from patterns |
| `/OAL:code-review` | Quality | Deep code review |
| `/OAL:security-review` | Security | Security vulnerability scanning |
| `/OAL:ship` | Delivery | Ship pipeline (idea → PR) |
| `/OAL:handoff` | Collaboration | Session transfer |
| `/OAL:maintainer` | OSS | Open-source maintainer tools |
| `/OAL:sequential-thinking` | Thinking | Structured reasoning |
| `/OAL:ralph-start` | Automation | Start Ralph loop |
| `/OAL:ralph-stop` | Automation | Stop Ralph loop |

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
/OAL:deep-plan implement OAuth2 flow
/OAL:learn from this session
/OAL:code-review src/auth.ts
```

### Creating Custom Plugins

1. Create `plugins/my-plugin/plugin.json`
2. Add commands to `plugins/my-plugin/commands/`
3. OAL auto-discovers plugins on startup

See `plugins/advanced/` for examples.

## Migration from Superpowers

Advanced commands are OAL-native equivalents of superpowers capabilities:

| Superpowers | OAL Advanced |
|-------------|--------------|
| `writing-plans` | `/OAL:deep-plan` |
| `learner` | `/OAL:learn` |
| `requesting-code-review` | `/OAL:code-review` |
| `security-review` | `/OAL:security-review` |
| `finishing-a-development-branch` | `/OAL:ship` |
| `handoff` | `/OAL:handoff` |

OAL advanced commands are designed for OAL standalone mode without requiring external plugins.
