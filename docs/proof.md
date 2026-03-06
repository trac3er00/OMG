# OMG Proof Surface

## Verification

OMG keeps verification visible instead of burying it in implementation details.

- Current local full-suite result: `2444 passed, 2 skipped` on March 6, 2026.
- Full-suite verification is run before release.
- Setup and trust-release behavior have targeted regression tests.
- Compatibility remains covered, but `compat` is no longer the onboarding story.

## Provider Matrix

| Provider | Detect | Auth Check | MCP Config | Host Priority |
|----------|--------|------------|------------|---------------|
| Claude Code | host-native | host-native | yes | primary |
| Codex | yes | yes | yes | primary |
| OpenCode | yes | yes | yes | primary |
| Gemini | yes | yes | yes | supported |
| Kimi | yes | yes | yes | supported |

## Adoption Evidence

- Native setup writes `.omg/state/adoption-report.json`
- Native setup writes `.omg/state/cli-config.yaml`
- `OMG-only` and `coexist` are both covered in setup tests

## HUD

Reference artifact:

![OMG HUD](/Users/cminseo/Documents/scripts/Shell/OMG/docs/assets/omg-hud.svg)

## Benchmarks

Representative benchmark tasks for this trust release:

- host detection and auth wiring
- adoption detection with overlapping ecosystems
- plugin install and uninstall correctness
- `crazy` orchestration smoke coverage

## Sample Transcripts

- Setup: [docs/transcripts/setup.md](/Users/cminseo/Documents/scripts/Shell/OMG/docs/transcripts/setup.md)
- Crazy: [docs/transcripts/crazy.md](/Users/cminseo/Documents/scripts/Shell/OMG/docs/transcripts/crazy.md)
