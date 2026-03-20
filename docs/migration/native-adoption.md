# Native Adoption for OMC, OMX, and Superpowers

OMG keeps adoption native to OMG. There is no public `migrate` command to memorize or map back to another project.

Use the launcher-first flow:

- `npx omg env doctor`
- `npx omg install --plan`
- `npx omg install --apply`

Legacy compatibility paths remain available when you need them:

- `/OMG:setup`
- `./OMG-setup.sh install --adopt=auto`

## What Setup Detects

Setup can detect compatibility markers from:

- OMC-style environments
- OMX-style environments
- Superpowers-style command, skill, or workspace surfaces

Those detections are treated as adoption context, not as public implementation detail.

## Adoption Modes

### OMG-only

Recommended for most users.

- OMG becomes the primary hooks, HUD, MCP, and orchestration layer.
- Portable state is preserved where safe and overlapping surfaces are backed up before replacement.
- `compat` remains available for legacy skill routing only.

### coexist

Advanced mode for careful landings.

- OMG avoids claiming ownership of third-party namespaces.
- Existing HUD and hook ownership stays intact unless you explicitly switch later.
- Conflicts are recorded in the adoption report instead of being overwritten.

## Output

Native adoption writes:

- `.omg/state/adoption-report.json`
- `.omg/state/cli-config.yaml`
- `.mcp.json`

## Choosing a Preset

- `safe`: conservative OMG baseline
- `balanced`: recommended daily workflow
- `interop`: stronger shared-memory and multi-host interop
- `labs`: enables the most opinionated experimentation surfaces

## What Changes for Existing Users

- OMG-native setup language replaces public migration language.
- Compatibility references remain documented so users coming from OMC, OMX, or Superpowers can understand what setup detected.
- Public onboarding is launcher-first: `npx omg env doctor` / `npx omg install --plan` / `npx omg install --apply`. Legacy Claude aliases (`/OMG:setup`, `/OMG:crazy`) remain available.
