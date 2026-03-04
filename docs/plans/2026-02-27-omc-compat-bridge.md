# Legacy Compatibility Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use OMG:deep-plan to implement this plan task-by-task.

**Gomg:** Ensure every legacy skill name can be invoked in OMG standalone mode without external legacy installation.

**Architecture:** Add a runtime compatibility dispatcher that maps legacy skill names to OMG-native execution routes. Expose this dispatcher via `omg compat list` and `omg compat run`, and enforce coverage with tests that compare against OMG's internal legacy skill contract tables.

**Tech Stack:** Python 3.12, pytest, existing OMG runtime/hooks modules.

---

### Task 1: Define legacy skill mapping contract

**Files:**
- Create: `/Users/cminseo/Documents/scripts/Shell/OMG/runtime/omc_compat.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_omc_compat.py`

**Step 1: Write failing test**
- Assert all legacy skills in OMG contract tables are listed by the compat module.

**Step 2: Run failing test**
- `PYENV_VERSION=3.12.7 python -m pytest -q tests/runtime/test_omc_compat.py`

**Step 3: Implement mapping**
- Add `LEGACY_SKILL_ROUTES` table for all 37 skills.
- Add `list_omc_skills()`.

**Step 4: Re-run test**
- Expect pass.

### Task 2: Implement dispatch execution paths

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/runtime/omc_compat.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/runtime/test_omc_compat.py`

**Step 1: Write failing tests**
- For representative skills (`omg-teams`, `ccg`, `pipeline`, `note`, `omg-doctor`), assert `status=ok`.

**Step 2: Run failing tests**
- Same pytest target.

**Step 3: Implement minimal handlers**
- Route team skills via `runtime/team_router.py`.
- Route runtime skills via `runtime/dispatcher.py`.
- Route pipeline via `lab/pipeline.py`.
- Route state/memory skills via `.omg/state` writes.

**Step 4: Re-run tests**
- Expect pass.

### Task 3: Expose compat in CLI

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/scripts/omg.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/scripts/test_omg_cli.py`

**Step 1: Write failing CLI tests**
- `omg compat list` returns count and skills.
- `omg compat run --skill omc-teams ...` returns compat schema.

**Step 2: Run failing tests**
- `PYENV_VERSION=3.12.7 python -m pytest -q tests/scripts/test_omg_cli.py`

**Step 3: Implement CLI subcommands**
- Add `omc list`, `omc run`.

**Step 4: Re-run tests**
- Expect pass.

### Task 4: Add coverage and validate end-to-end

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/e2e/test_standalone_ga.py`
- Create: `/Users/cminseo/Documents/scripts/Shell/OMG/tests/e2e/test_omc_skill_coverage.py`

**Step 1: Write failing coverage test**
- For each skill in OMG legacy contract tables, dispatch via compat and expect non-error.

**Step 2: Run failing tests**
- `PYENV_VERSION=3.12.7 python -m pytest -q tests/e2e/test_omc_skill_coverage.py`

**Step 3: Implement/adjust handlers**
- Fill any missing branches.

**Step 4: Run full suite**
- `PYENV_VERSION=3.12.7 python -m pytest -q`
- Expect all green.
