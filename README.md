# OMG

[![Compat Gate](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml/badge.svg)](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml)
[![npm version](https://img.shields.io/npm/v/%40trac3er%2Foh-my-god)](https://www.npmjs.com/package/@trac3er/oh-my-god)
[![License](https://img.shields.io/github/license/trac3er00/OMG)](LICENSE)

OMG upgrades your agent host instead of replacing it. It gives Claude Code, Codex, and other supported CLIs a tighter setup flow, stronger orchestration, native adoption from older plugin stacks, and proof-backed verification.

- Brand: `OMG`
- Repo: `https://github.com/trac3er00/OMG`
- npm: `@trac3er/oh-my-god`
- Plugin id: `omg`
- Marketplace id: `omg`

## Why OMG

- Claude front door: install, run `/OMG:setup`, then `/OMG:crazy <goal>`.
- Multi-host support: Claude Code and Codex (canonical), Gemini CLI and Kimi CLI (compatibility providers).
- Compiled planning: advanced planning is now compiled into the `plan-council` bundle for deterministic execution.
- Native adoption: setup detects OMC, OMX, and Superpowers-style environments without exposing copycat public migration commands.
- Proof-first delivery: verification, provider coverage, HUD artifacts, and transcripts are published instead of implied.

## Canonical Contract

OMG now ships a production control-plane contract and generated host artifacts. Same-machine production support is anchored by the stdio-first `omg-control` MCP. HTTP control-plane exposure is intended for development and local HUD use only.

- Normative spec: `OMG_COMPAT_CONTRACT.md`
- Executable registry: `registry/omg-capability.schema.json` and `registry/bundles/*.yaml`
- Generated Codex pack: `.agents/skills/omg/`
- Validation: `python3 scripts/omg.py contract validate`
- Compilation: `python3 scripts/omg.py contract compile --host claude --host codex --channel public`
- Release gate: `python3 scripts/omg.py release readiness --channel dual`

![OMG HUD](docs/assets/omg-hud.svg)

## Quickstart

Install with npm:

```bash
npm install @trac3er/oh-my-god
```

That fast path now does two things:

- registers the local `omg` marketplace plus `omg@omg` plugin bundle for Claude Code
- wires `omg-control` into detected Codex, Gemini, and Kimi MCP configs using the managed OMG Python runtime

Or clone and run the setup manager:

```bash
git clone https://github.com/trac3er00/OMG
cd OMG
chmod +x OMG-setup.sh
./OMG-setup.sh install --mode=omg-only --preset=balanced
```

Then run:

```text
/OMG:setup
/OMG:crazy stabilize auth and dashboard flows
```

On non-Claude hosts, verify native MCP registration instead:

- `codex mcp list`
- `gemini mcp list`
- `kimi mcp list`

Success looks like:

- supported hosts are detected
- Claude Code sees `omg@omg` as enabled instead of `failed to load`
- Claude Code's plugin bundle owns `filesystem` and `omg-control` without duplicate warnings from top-level `.mcp.json`
- `~/.claude/settings.json` has a `statusLine` command for `~/.claude/hud/omg-hud.mjs`
- `~/.codex/config.toml`, `~/.gemini/settings.json`, and `~/.kimi/mcp.json` receive `omg-control` when those CLIs are on `PATH`
- additional MCP servers are added when a broader preset is selected (`balanced` adds `context7`; `interop` adds `websearch` and `omg-memory`; `labs` adds browser automation)
- `.omg/state/adoption-report.json` is written when another ecosystem is present
- OMG reports the selected preset and next step

## Install Guides

- Claude Code: [docs/install/claude-code.md](docs/install/claude-code.md)
- Codex: [docs/install/codex.md](docs/install/codex.md)
- Gemini: [docs/install/gemini.md](docs/install/gemini.md)
- Kimi: [docs/install/kimi.md](docs/install/kimi.md)
## Native Adoption

OMG uses native setup language instead of public migration commands.

- `OMG-only`: recommended. OMG becomes the primary hooks, HUD, MCP, and orchestration layer.
- `coexist`: advanced. OMG preserves non-conflicting third-party surfaces and records overlap instead of overwriting it.
- Modes: `chill`, `focused`, `exploratory`. `focused` is the production default.
- Presets: `safe`, `balanced`, `interop`, `labs`.

## Security Notes

- The shipped `safe` preset now registers pre-tool security hooks before the planning helper.
- `Bash` requests are screened by `firewall.py`, and file reads or edits are screened by `secret-guard.py`.
- Raw environment dumps, interpreters, and permission-changing commands such as `env`, `node`, `python`, `python3`, `chmod`, and `chown` now require approval instead of being silently allowed.

Compatibility references to OMC, OMX, and Superpowers are documented here: [docs/migration/native-adoption.md](docs/migration/native-adoption.md)

## Proof

Current local verification for this release: See `.omg/evidence/` for machine-generated verification artifacts.

- Truth bundles: `claim-judge`, `test-intent-lock`, `proof-gate`
- Verification and provider matrix: [docs/proof.md](docs/proof.md)
- Sample setup transcript: [docs/transcripts/setup.md](docs/transcripts/setup.md)
- Sample crazy transcript: [docs/transcripts/crazy.md](docs/transcripts/crazy.md)
- Release process: [docs/release-checklist.md](docs/release-checklist.md)

## Command Surface

Primary entry points:

- `/OMG:setup`
- `/OMG:crazy`
- `/OMG:deep-plan` (compatibility path to `plan-council`)

Advanced surfaces stay available for deeper workflows:

- `/OMG:security-check`
- `/OMG:api-twin`
- `/OMG:preflight`
- `/OMG:teams`
- `/OMG:ccg`
- `/OMG:compat`
- `/OMG:ship`

## Contributing

Public contributions are welcome.

- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reporting: [SECURITY.md](SECURITY.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

## Positioning

OMG is a plugin and orchestration layer for supported CLIs. It is not a base-model training project. The goal is to make frontier agent hosts tighter, safer, more interoperable, and more verifiable than the default experience.
