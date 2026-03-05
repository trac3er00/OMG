# Plugin Command Surface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove `omg:OMG:*` command stutter and local marketplace clone duplication without changing the standalone `/OMG:*` command surface.

**Architecture:** Rename repo command source files to plain names, keep standalone command names stable by prefixing `OMG:` during install, and gate marketplace registration/sync behind a local-source check in `OMG-setup.sh`.

**Tech Stack:** Bash, Markdown command docs, JSON plugin manifests, pytest.

---

### Task 1: Lock the new source command contract with failing tests

**Files:**
- Modify: `/tmp/omg-plugin-fixes/tests/commands/test_alias_compat.py`
- Modify: `/tmp/omg-plugin-fixes/tests/test_ralph.py`
- Test: `/tmp/omg-plugin-fixes/tests/commands/test_alias_compat.py`
- Test: `/tmp/omg-plugin-fixes/tests/test_ralph.py`

**Step 1: Write the failing tests**

- Assert source command docs exist at `commands/teams.md`, `commands/ccg.md`, `commands/escalate.md`, `commands/ralph-start.md`, and `commands/ralph-stop.md`.
- Assert the old prefixed source filenames no longer exist.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/commands/test_alias_compat.py tests/test_ralph.py`

Expected: FAIL because the repo still stores `commands/OMG:*.md`.

**Step 3: Write minimal implementation**

- Rename the affected source command docs and update direct path references.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/commands/test_alias_compat.py tests/test_ralph.py`

Expected: PASS.

### Task 2: Lock standalone install behavior and local plugin cache behavior

**Files:**
- Modify: `/tmp/omg-plugin-fixes/tests/e2e/test_setup_script.py`
- Test: `/tmp/omg-plugin-fixes/tests/e2e/test_setup_script.py`

**Step 1: Write the failing tests**

- Assert a standalone install still writes only `OMG:` command filenames into `~/.claude/commands`.
- Assert `install --install-as-plugin` from the local repo does not create `plugins/marketplaces/oh-my-god` or `plugins/known_marketplaces.json`.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/e2e/test_setup_script.py -k "omg_only_command_surface or local_source_plugin_install"`

Expected: FAIL because install copies prefixed source files directly and currently seeds marketplace metadata.

**Step 3: Write minimal implementation**

- Teach the installer to map source command docs to `OMG:` target filenames.
- Skip marketplace registration/sync for local source installs.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/e2e/test_setup_script.py -k "omg_only_command_surface or local_source_plugin_install"`

Expected: PASS.

### Task 3: Update plugin manifests and install helpers

**Files:**
- Modify: `/tmp/omg-plugin-fixes/plugins/core/plugin.json`
- Modify: `/tmp/omg-plugin-fixes/plugins/advanced/plugin.json`
- Modify: `/tmp/omg-plugin-fixes/OMG-setup.sh`
- Modify: `/tmp/omg-plugin-fixes/.claude-plugin/scripts/uninstall.sh`

**Step 1: Write the failing tests**

- Reuse the manifest/path and setup-script assertions from Tasks 1 and 2.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/commands/test_alias_compat.py tests/test_ralph.py tests/e2e/test_setup_script.py -k "omg_only_command_surface or local_source_plugin_install"`

Expected: FAIL until manifests and installer logic match the new layout.

**Step 3: Write minimal implementation**

- Point manifest command paths at plain source filenames.
- Keep uninstall cleanup targeting the installed `OMG:` filenames.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q tests/commands/test_alias_compat.py tests/test_ralph.py tests/e2e/test_setup_script.py -k "omg_only_command_surface or local_source_plugin_install"`

Expected: PASS.

### Task 4: Full targeted verification and delivery

**Files:**
- Modify if needed: `/tmp/omg-plugin-fixes/README.md`

**Step 1: Run targeted verification**

Run: `python3 -m pytest -q tests/commands/test_alias_compat.py tests/test_ralph.py tests/e2e/test_setup_script.py tests/test_claude_plugin_manifest.py`

Expected: PASS.

**Step 2: Inspect git diff**

Run: `git status --short && git diff --stat`

Expected: Only the command-surface and install-flow changes are present.

**Step 3: Commit and publish**

- Commit with a focused message.
- Push `fix-plugin-command-surface`.
- Open a PR against `main`.
