# OMG Command Reference

Quick reference for all OMG slash commands with examples.

## Core Commands

### `/OMG:init` — Project Setup
```
/OMG:init                    # Auto-detect: new project, domain, or health check
/OMG:init payment            # Scaffold new domain from existing patterns
/OMG:init setup              # Run adoption wizard (CLI detection, preset, MCP)
/OMG:init setup --preset balanced --non-interactive
```

### `/OMG:validate` — System Validation
```
/OMG:validate                # Full validation (doctor + health + plugins)
/OMG:validate doctor         # Runtime & install checks
/OMG:validate health         # Project health (profile, secrets, tools)
/OMG:validate plugins        # Plugin interop diagnostics
/OMG:validate doctor --fix   # Auto-repair known issues
```

### `/OMG:issue` — Security Diagnostics
```
/OMG:issue                           # Full scan (4 sub-agents)
/OMG:issue --agents red-team         # Specific agent only
/OMG:issue --format sarif            # SARIF output for CI
/OMG:issue --surfaces plugin_interop # Legacy surface scan
```

### `/OMG:crazy` — Multi-Agent Orchestration
```
/OMG:crazy fix the auth middleware   # Full CRAZY mode
/OMG:crazy ccg review this stack     # Tri-track (backend/frontend/arch)
/OMG:crazy team codex debug auth     # Route to specific model
```

### `/OMG:ralph` — Autonomous Loop
```
/OMG:ralph start fix all tests       # Start autonomous execution
/OMG:ralph stop                      # Stop the loop
/OMG:ralph status                    # Check current state
```

### `/OMG:deep-plan` — Strategic Planning
```
/OMG:deep-plan redesign the payment system
```

### `/OMG:ship` — Idea to PR
```
/OMG:ship add rate limiting to the API
```

## Analytics & Cost

### `/OMG:stats` — Session Analytics
```
/OMG:stats                   # Current session summary
/OMG:stats weekly            # 7-day trend analysis
/OMG:stats files             # File interaction heatmap
/OMG:stats failures          # Failure pattern analysis
/OMG:stats dashboard         # Generate HTML dashboard
/OMG:stats cost              # Cost tracking summary
/OMG:stats cost budget       # Budget config and thresholds
/OMG:stats cost reset        # Clear cost ledger
```

## Session Management

### `/OMG:session` — State Branches
```
/OMG:session branch --name "experiment"
/OMG:session fork --from <snapshot_id> --name "alt"
/OMG:session merge --from "experiment" --into "main"
/OMG:session merge --from "experiment" --preview
```

## Security & Dependencies

### `/OMG:security-check` — Full Security Pipeline
```
/OMG:security-check          # Full project security audit
/OMG:security-check app/     # Scoped to directory
```

### `/OMG:deps` — Dependency Health
```
/OMG:deps                    # Full health report
/OMG:deps cves               # CVE scan only
/OMG:deps licenses           # License compatibility
/OMG:deps outdated           # Outdated packages
```

## Utility Commands

| Command | Purpose |
|---------|---------|
| `/OMG:escalate codex "task"` | Route to Codex for deep work |
| `/OMG:escalate gemini "task"` | Route to Gemini for UI/UX |
| `/OMG:mode focused` | Set session mode (chill/focused/exploratory) |
| `/OMG:preset` | Inspect or apply preset |
| `/OMG:arch` | Dependency graphs and architecture diagrams |
| `/OMG:browser` | Browser automation (Playwright) |
| `/OMG:forge` | Labs-only domain prototyping |
| `/OMG:api-twin` | Contract replay and API simulation |
| `/OMG:preflight` | Risk classification and route planning |
| `/OMG:profile-review` | Review governed preferences |
| `/OMG:create-agent` | Create custom agent definitions |
| `/OMG:ai-commit` | Analyze changes and propose atomic commits |

## CLI (npx)

```bash
npx @trac3r/oh-my-god quickstart           # One-shot setup
npx @trac3r/oh-my-god quickstart --level 2  # Full install
npx @trac3r/oh-my-god install --plan        # Preview install plan
npx @trac3r/oh-my-god doctor --format json  # Runtime checks
npx @trac3r/oh-my-god validate             # Full validation
```
