# OMG 2.0.4

[![Compat Gate](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml/badge.svg)](https://github.com/trac3er00/OMG/actions/workflows/omg-compat-gate.yml)
[![npm version](https://img.shields.io/npm/v/%40trac3er%2Foh-my-god)](https://www.npmjs.com/package/@trac3er/oh-my-god)
[![License](https://img.shields.io/github/license/trac3er00/OMG)](LICENSE)

OMG upgrades your agent host instead of replacing it. It gives Claude Code, Codex, and other supported CLIs a tighter setup flow, stronger orchestration, native adoption from older plugin stacks, and proof-backed verification.

- Brand: `OMG`
- Repo: `https://github.com/trac3er00/OMG`
- npm: `@trac3er/oh-my-god`
- Plugin id: `omg`
- Marketplace id: `omg`
- Version: `2.0.4`

## Why OMG

- Small front door: install, run `/OMG:setup`, then `/OMG:crazy <goal>`.
- Multi-host support: Claude Code, Codex, Gemini CLI, and Kimi CLI.
- Native adoption: setup detects OMC, OMX, and Superpowers-style environments without exposing copycat public migration commands.
- Proof-first delivery: verification, provider coverage, HUD artifacts, and transcripts are published instead of implied.

## Canonical Contract

OMG now ships a production control-plane contract and generated host artifacts.

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

Success looks like:

- supported hosts are detected
- `.mcp.json` is configured
- `.mcp.json` includes both `omg-memory` and stdio `omg-control`
- `.omg/state/adoption-report.json` is written when another ecosystem is present
- OMG reports the selected preset and next step

## Install Guides

- Claude Code: [docs/install/claude-code.md](docs/install/claude-code.md)
- Codex: [docs/install/codex.md](docs/install/codex.md)
## Native Adoption

OMG uses native setup language instead of public migration commands.

- `OMG-only`: recommended. OMG becomes the primary hooks, HUD, MCP, and orchestration layer.
- `coexist`: advanced. OMG preserves non-conflicting third-party surfaces and records overlap instead of overwriting it.
- Presets: `safe`, `balanced`, `interop`, `labs`.

## Security Notes

- The shipped `safe` preset now registers pre-tool security hooks before the planning helper.
- `Bash` requests are screened by `firewall.py`, and file reads or edits are screened by `secret-guard.py`.
- Raw environment dumps, interpreters, and permission-changing commands such as `env`, `node`, `python`, `python3`, `chmod`, and `chown` now require approval instead of being silently allowed.

Compatibility references to OMC, OMX, and Superpowers are documented here: [docs/migration/native-adoption.md](docs/migration/native-adoption.md)

## Proof

Current local verification for this release: `2466 passed, 2 skipped` on March 7, 2026.

- Verification and provider matrix: [docs/proof.md](docs/proof.md)
- Sample setup transcript: [docs/transcripts/setup.md](docs/transcripts/setup.md)
- Sample crazy transcript: [docs/transcripts/crazy.md](docs/transcripts/crazy.md)
- Release process: [docs/release-checklist.md](docs/release-checklist.md)

## Command Surface

Primary entry points:

- `/OMG:setup`
- `/OMG:crazy`

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
