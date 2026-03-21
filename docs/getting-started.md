# Getting Started with OMG

> Zero to working in 5 minutes.

## Prerequisites

- Python 3.10+
- Node.js 18+ (for `npx`)
- Git
- One of: Claude Code, Codex, Gemini CLI, Kimi, OpenCode

## Quick Install

```bash
# One-liner install
npx @trac3r/oh-my-god quickstart

# Or with specific tier
npx @trac3r/oh-my-god quickstart --level 2 --preset balanced
```

### Install Tiers

| Level | What's Included | Time |
|-------|----------------|------|
| **1 (Essential)** | Hooks, commands, rules | ~60s |
| **2 (Full)** | Level 1 + MCP servers, agents, venv | ~2min |
| **3 (Enterprise)** | Level 2 + all presets, multi-host config | ~3min |

## Manual Install

```bash
git clone https://github.com/trac3r00/OMG.git
cd OMG
./OMG-setup.sh install
```

## Verify Installation

```bash
# Run the doctor
/OMG:validate doctor

# Full validation
/OMG:validate
```

## First Steps

### 1. Initialize your project

```
/OMG:init
```

This auto-detects your project type and creates:
- `.omg/state/profile.yaml` — project profile
- `.omg/state/quality-gate.json` — lint/test/format commands
- `.omg/knowledge/` — decision logs and patterns

### 2. Try a security scan

```
/OMG:issue
```

### 3. Start working

```
/OMG:crazy implement user authentication
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `/OMG:init` | Project setup, domain scaffolding |
| `/OMG:validate` | Doctor + health checks + plugin diagnostics |
| `/OMG:issue` | Security scanning with 4 sub-agents |
| `/OMG:crazy` | Multi-agent orchestration (Claude + Codex + Gemini) |
| `/OMG:ralph start` | Autonomous loop execution |
| `/OMG:stats` | Session analytics + cost tracking |
| `/OMG:deep-plan` | Strategic planning |
| `/OMG:ship` | Idea to PR pipeline |

## Next Steps

- [Command Reference](command-surface.md)
- [Troubleshooting](troubleshooting.md)
- [Migration from OMC/Superpowers](migration/native-adoption.md)
- Per-host install: [Claude Code](install/claude-code.md) | [Codex](install/codex.md) | [Gemini](install/gemini.md)
