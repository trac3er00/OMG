# Upstream Influence Notes

- Upstream project: `oh-my-claudecode`
- Source URL: `https://github.com/Yeachan-Heo/oh-my-claudecode`
- Integration strategy: `OMG-native adapters and compatibility layer (no vendored source trees)`
- Initial research baseline commit hash: `8234e6d8fe346bb518e44cb9bf1f2c7cc0f1d716`
- First influence capture (UTC): `2026-02-27`

## Local Policy

1. Keep OMG runtime and compatibility behavior implemented in OMG-owned code.
2. Use upstream repositories as references only, not as vendored source payload.
3. Record major intentional divergence here.

## Divergence Summary

- OMG introduces standalone routing and state migration (`.omc -> .omg`).
- OMG keeps command aliases (`/omc-teams`, `/ccg`) as compatibility wrappers.
- OMG defaults to `.omg` as canonical runtime state path.
- OMG adds optional ecosystem sync (`omg ecosystem`) for external plugin references.
