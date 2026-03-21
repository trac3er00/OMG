# Migration Guide — Moving to OMG

## From Superpowers

Superpowers and OMG can coexist (`--mode=coexist`). Key differences:

| Superpowers | OMG Equivalent |
|---|---|
| 7-phase workflow | `/OMG:deep-plan` + `/OMG:start-work` |
| Auto-updating skills | `/OMG:preset` + agent store |
| Socratic brainstorming | `/OMG:crazy` (multi-track) |
| TDD enforcement | `/OMG:mode tdd` |
| Code review skill | `/OMG:issue` (red-team + deps + security) |

**Steps:**
1. Install OMG: `./OMG-setup.sh install --mode=coexist`
2. Run `/OMG:validate` to check for hook conflicts
3. Gradually replace Superpowers skills with OMG commands
4. When ready: `./OMG-setup.sh install --mode=omg-only`

## From oh-my-claudecode (OMC)

| OMC | OMG Equivalent |
|---|---|
| `$team N` | `/OMG:crazy team N` |
| `$autopilot` | `/OMG:ralph start` |
| `$ultrawork` | `/OMG:crazy` |
| `omc ask codex` | `/OMG:escalate codex` |
| Ralph loop | `/OMG:ralph start [goal]` |
| `omc deep-interview` | `/OMG:deep-plan` |

**Steps:**
1. Install OMG alongside OMC: `./OMG-setup.sh install --mode=coexist`
2. OMG auto-detects OMC installation and avoids hook conflicts
3. Test with `/OMG:validate plugins`
4. Migrate workflows one at a time

## From oh-my-codex (OMX)

| OMX | OMG Equivalent |
|---|---|
| `omx team N:role` | `/OMG:crazy team` |
| `$ralph` | `/OMG:ralph start` |
| `omx deep-interview` | `/OMG:deep-plan` |
| `omx ask` | `/OMG:escalate` |

**Steps:**
1. Install: `./OMG-setup.sh install --adopt=auto`
2. OMG detects Codex CLI and configures `omg-control` MCP
3. Verify: `/OMG:validate`

## Common Post-Migration Steps

1. Run `/OMG:validate all` to verify complete installation
2. Set your preset: `/OMG:preset balanced` (or `safe`, `labs`, etc.)
3. Try `/OMG:deep-plan` on your next feature to see the planning workflow
4. Use `/OMG:stats` to track session analytics
