# Python Version Mismatch Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the review findings around Python prerequisite drift, incomplete hook compatibility updates, and weak regression coverage before opening the PR.

**Architecture:** Update the generator-owned install fast-path content at the shared source, extend release-surface drift checks so generated install docs are verified in `check_only` mode, and complete the remaining Python 3.9-safe hook entrypoints by postponing annotation evaluation. Lock those behaviors with focused regression tests first.

**Tech Stack:** Python, pytest, generated markdown docs, release-surface compiler.

---

### Task 1: Add failing regression tests

**Files:**
- Modify: `tests/runtime/test_release_surface_compiler.py`
- Modify: `tests/hooks/test_hook_command_targets.py`
- Modify: `tests/e2e/test_setup_script.py`

**Step 1: Write the failing tests**
- Assert generated install fast-path content includes both `Node >=18` and `Python >=3.10`.
- Assert `compile_release_surfaces(..., check_only=True)` reports drift when an install guide fast-path block is tampered with.
- Assert the remaining hook entrypoints called out in review contain `from __future__ import annotations`.
- Replace the source-text-only `omg.py` version-gate test with a subprocess/runtime assertion that simulates Python 3.9.

**Step 2: Run tests to verify they fail**
- Run: `pytest -q tests/runtime/test_release_surface_compiler.py tests/hooks/test_hook_command_targets.py tests/e2e/test_setup_script.py -k 'install_fast_path or version_gate or future_import'`
- Expected: failures on stale generator content and missing `__future__` imports.

### Task 2: Patch shared implementation

**Files:**
- Modify: `runtime/release_surface_compiler.py`
- Modify: `docs/install/claude-code.md`
- Modify: `docs/install/codex.md`
- Modify: `docs/install/gemini.md`
- Modify: `docs/install/kimi.md`
- Modify: `docs/install/opencode.md`
- Modify: `docs/install/github-app.md`
- Modify: `hooks/prompt-enhancer.py`
- Modify: `hooks/idle-detector.py`

**Step 1: Write minimal implementation**
- Update the shared install fast-path template to mention Python 3.10.
- Extend release-surface drift checking to validate all generated install guide fast-path markers.
- Add postponed annotation evaluation to the remaining hook entrypoints.
- Refresh generated install guide blocks so committed docs match the generator.

**Step 2: Run targeted tests**
- Run the same focused pytest command and confirm green.

### Task 3: Verify end-to-end

**Files:**
- No additional code changes expected.

**Step 1: Run final targeted verification**
- Run: `pytest -q tests/runtime/test_release_surface_compiler.py tests/hooks/test_hook_command_targets.py tests/e2e/test_setup_script.py`
- Run: `git diff --stat`

**Step 2: Confirm no remaining review blockers**
- Check generator, generated docs, hook entrypoints, and tests all agree on the Python prerequisite story.
