# Native Adoption for OMC, OMX, and Superpowers

OMG does not expose public `migrate` commands. Adoption is handled through `/OMG:setup` and `OMG-setup.sh`.

## What Setup Detects

- OMC-style markers
- OMX-style markers
- Superpowers-style command and skill surfaces

## Adoption Modes

### OMG-only

Recommended for most users.

- OMG becomes the primary hooks, HUD, MCP, and orchestration layer.
- Overlapping surfaces are backed up before OMG disables or replaces them where safe.
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
