# OMC Upstream Integration Notes

- Upstream project: `oh-my-claudecode`
- Source URL: `https://github.com/Yeachan-Heo/oh-my-claudecode`
- Import strategy: `vendor/omc + adapter layer`
- Initial imported commit hash: `8234e6d8fe346bb518e44cb9bf1f2c7cc0f1d716`
- Imported at (UTC): `2026-02-27`

## Local Policy

1. Keep `vendor/omc` as close to upstream as possible.
2. Apply OAL custom behavior in OAL-owned adapters/hooks/commands.
3. Record all intentional divergence here.

## Divergence Summary

- OAL introduces standalone routing and state migration (`.omc -> .oal`).
- OAL keeps command aliases (`/omc-teams`, `/ccg`) as compatibility wrappers.
- OAL defaults to `.oal` as canonical runtime state path.
- OAL adds optional ecosystem sync (`oal ecosystem`) for external plugin references.
