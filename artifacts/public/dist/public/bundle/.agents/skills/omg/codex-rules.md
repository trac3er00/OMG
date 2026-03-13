# OMG Codex Rules (channel: public)

## Defaults

- `cached_web_search: prefer_cached`
- `live_network: deny_by_default`
- `destructive_approval: required`

## Protected Paths

- `.omg/**`
- `.agents/**`
- `.codex/**`
- `.claude/**`

## Required Skills

- `omg/control-plane`
- `omg/mcp-fabric`

## Host Interop

- Respect the repo `AGENTS.md` / `AGENTS.override.md` chain before applying OMG-specific rules.
- Keep OMG guidance separate from Codex built-in slash commands.

## Protected Planning Surface

- `omg/plan-council` (explicit invocation only)

## Approval Matrix

| Action | Approval Required |
|--------|------------------|
| Read / Grep | No |
| Write to protected paths | Yes |
| Bash (python3:*) | Yes (balanced+ tier) |
| git push --force | Yes |
| Production deploy | Yes |
