# OMG 2.0.1

OMG upgrades your agent host instead of replacing it. It gives Claude Code, Codex, OpenCode, and other supported CLIs a tighter setup flow, stronger orchestration, adoption paths from older plugin stacks, and proof-backed verification.

- Brand: `OMG`
- Repo: `https://github.com/trac3er00/OMG`
- npm: `@trac3er/oh-my-god`
- Plugin id: `omg`
- Marketplace id: `omg`
- Version: `2.0.1`

## The Front Door

OMG keeps the public journey small:

1. Install for your host.
2. Run `/OMG:setup`.
3. Run `/OMG:crazy <goal>`.

Everything else is still available, but `setup` and `crazy` are the native OMG entrypoints.

## What OMG Does

- Upgrades Claude Code, Codex, and OpenCode with a shared orchestration layer.
- Detects overlapping ecosystems and offers native OMG adoption instead of public migration commands.
- Supports two adoption modes:
  - `OMG-only`: recommended. OMG becomes the primary hooks, HUD, MCP, and orchestration layer.
  - `coexist`: advanced. OMG preserves other ecosystems where possible and avoids destructive overlap.
- Presets reduce feature-flag sprawl:
  - `safe`
  - `balanced`
  - `interop`
  - `labs`
- Keeps `compat` available for legacy skill routing without making it the main onboarding story.

## Supported Hosts

- Claude Code
- Codex
- OpenCode
- Gemini CLI
- Kimi CLI

Claude Code, Codex, and OpenCode are the primary top-level install journeys in this release.

## Install

### npm

```bash
npm install @trac3er/oh-my-god
```

### git

```bash
git clone https://github.com/trac3er00/OMG
cd OMG
chmod +x OMG-setup.sh
./OMG-setup.sh install
```

### Host Guides

- Claude Code: [docs/install/claude-code.md](/Users/cminseo/Documents/scripts/Shell/OMG/docs/install/claude-code.md)
- Codex: [docs/install/codex.md](/Users/cminseo/Documents/scripts/Shell/OMG/docs/install/codex.md)
- OpenCode: [docs/install/opencode.md](/Users/cminseo/Documents/scripts/Shell/OMG/docs/install/opencode.md)

## Native Adoption

OMG can adopt setups coming from OMC, OMX, and Superpowers-style environments through `/OMG:setup` and `OMG-setup.sh`.

- It detects overlapping ecosystems internally.
- It writes an adoption report to `.omg/state/adoption-report.json`.
- It recommends `OMG-only` and keeps `coexist` available when you want a non-destructive landing.

Details: [docs/migration/native-adoption.md](/Users/cminseo/Documents/scripts/Shell/OMG/docs/migration/native-adoption.md)

## Proof

Trust is a product surface. OMG publishes proof for:

- current verification results
- verification status
- provider coverage
- adoption evidence
- HUD artifact
- sample transcripts

Current local verification for this release: `2444 passed, 2 skipped` on March 6, 2026.

See [docs/proof.md](/Users/cminseo/Documents/scripts/Shell/OMG/docs/proof.md).

## Commands

Primary:

- `/OMG:setup`
- `/OMG:crazy`

Advanced:

- `/OMG:teams`
- `/OMG:ccg`
- `/OMG:compat`
- `/OMG:ship`
- `/OMG:security-review`

## Positioning

OMG is a plugin and orchestration layer for supported CLIs. It is not a base-model training project. The goal is to make frontier agent hosts tighter, safer, more interoperable, and more verifiable than the default experience.
