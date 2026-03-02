# OMC Compatibility Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure every OMC skill name can be invoked in OAL standalone mode without external OMC installation.

**Architecture:** Add a runtime compatibility dispatcher that maps OMC skill names to OAL-native execution routes. Expose this dispatcher via `oal omc list` and `oal omc run`, and enforce coverage with tests that compare against `vendor/omc/skills`.

**Tech Stack:** Python 3.12, pytest, existing OAL runtime/hooks modules.

---

### Task 1: Define OMC skill mapping contract

**Files:**
- Create: `/Users/cminseo/Documents/scripts/Shell/OAL/runtime/omc_compat.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/runtime/test_omc_compat.py`

**Step 1: Write failing test**
- Assert all skill directories under `vendor/omc/skills` are listed by compat module.

**Step 2: Run failing test**
- `PYENV_VERSION=3.12.7 python -m pytest -q tests/runtime/test_omc_compat.py`

**Step 3: Implement mapping**
- Add `OMC_SKILL_ROUTES` table for all 37 skills.
- Add `list_omc_skills()`.

**Step 4: Re-run test**
- Expect pass.

### Task 2: Implement dispatch execution paths

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/runtime/omc_compat.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/runtime/test_omc_compat.py`

**Step 1: Write failing tests**
- For representative skills (`omc-teams`, `ccg`, `pipeline`, `note`, `omc-doctor`), assert `status=ok`.

**Step 2: Run failing tests**
- Same pytest target.

**Step 3: Implement minimal handlers**
- Route team skills via `runtime/team_router.py`.
- Route runtime skills via `runtime/dispatcher.py`.
- Route pipeline via `lab/pipeline.py`.
- Route state/memory skills via `.oal/state` writes.

**Step 4: Re-run tests**
- Expect pass.

### Task 3: Expose compat in CLI

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/scripts/oal.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/scripts/test_oal_cli.py`

**Step 1: Write failing CLI tests**
- `oal omc list` returns count and skills.
- `oal omc run --skill omc-teams ...` returns compat schema.

**Step 2: Run failing tests**
- `PYENV_VERSION=3.12.7 python -m pytest -q tests/scripts/test_oal_cli.py`

**Step 3: Implement CLI subcommands**
- Add `omc list`, `omc run`.

**Step 4: Re-run tests**
- Expect pass.

### Task 4: Add coverage and validate end-to-end

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/e2e/test_standalone_ga.py`
- Create: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/e2e/test_omc_skill_coverage.py`

**Step 1: Write failing coverage test**
- For each skill in `vendor/omc/skills`, dispatch via compat and expect non-error.

**Step 2: Run failing tests**
- `PYENV_VERSION=3.12.7 python -m pytest -q tests/e2e/test_omc_skill_coverage.py`

**Step 3: Implement/adjust handlers**
- Fill any missing branches.

**Step 4: Run full suite**
- `PYENV_VERSION=3.12.7 python -m pytest -q`
- Expect all green.

