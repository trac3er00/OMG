# Plugin Command Surface Design

**Date:** 2026-03-05

**Problem**

Local OMG plugin installs currently create two avoidable artifacts:

1. Plugin-discovered command aliases inherit the `OMG:` filename prefix and become redundant names such as `omg:OMG:deps`.
2. `OMG-setup.sh install --install-as-plugin` seeds a full marketplace clone under `~/.claude/plugins/marketplaces/oh-my-god`, duplicating the source repo and plugin cache for local installs.

**Decision**

- Store source command docs with plain filenames such as `commands/deps.md`.
- Preserve the standalone user-facing command surface by having `OMG-setup.sh` install those files into `~/.claude/commands/OMG:deps.md`.
- Skip marketplace registration and marketplace sync when the plugin bundle is installed from a local source checkout.

**Why this approach**

- It removes the `omg:OMG:*` stutter at the source-file level without changing the standalone `/OMG:*` commands that the repo documents everywhere.
- It fixes the local cache duplication in the install path that users actually hit when working from a cloned repo.
- It avoids a wider breaking rename of the installed command surface.

**Risks**

- Plugin-only command aliases will change from `omg:OMG:*` to `omg:*` for any flow that indexes the source command files directly.
- Local source installs will no longer populate marketplace metadata; tests need to lock that behavior so the change is explicit.

**Verification**

- Command source tests should assert the repo now stores plain command filenames.
- Setup-script tests should assert standalone installs still create only `OMG:` command files.
- Plugin install tests should assert local source installs still register the plugin cache but do not create `plugins/marketplaces/oh-my-god` or `known_marketplaces.json`.
