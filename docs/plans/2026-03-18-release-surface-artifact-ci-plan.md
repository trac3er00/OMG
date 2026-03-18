# Release Surface Artifact CI Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make contract compilation emit the release-surface manifest into the uploaded artifact tree so the final release-readiness gate can validate it in CI.

**Architecture:** Reproduce the failure in `compile_contract_outputs()` with a targeted regression test, then add the smallest helper needed to write `release-surface.json` into `output_root/dist/<channel>/`. Keep the readiness gate unchanged so it continues validating the assembled artifact bundle rather than checkout state.

**Tech Stack:** Python, pytest, GitHub Actions workflow expectations, contract compiler, release-surface registry.

---

### Task 1: Add the failing regression

**Files:**
- Modify: `tests/runtime/test_contract_compiler.py`

**Step 1: Write the failing test**
- Assert `compile_contract_outputs(..., output_root=tmp_path, channel="public")` returns `ok`.
- Assert `tmp_path/dist/public/release-surface.json` exists and is referenced in the result artifacts.

**Step 2: Run the targeted test**
- Run: `python3 -m pytest -q -p no:cov -o addopts='' tests/runtime/test_contract_compiler.py -k release_surface_manifest`
- Expected: FAIL because the manifest is missing from `output_root/dist/public`.

### Task 2: Patch contract compilation

**Files:**
- Modify: `runtime/contract_compiler.py`

**Step 1: Write minimal implementation**
- Add a helper that writes the canonical release-surface manifest into `output_root/dist/<channel>/release-surface.json`.
- Call it from `compile_contract_outputs()` and include the emitted path in the returned artifacts.

**Step 2: Re-run the targeted test**
- Run: `python3 -m pytest -q -p no:cov -o addopts='' tests/runtime/test_contract_compiler.py -k release_surface_manifest`
- Expected: PASS.

### Task 3: Verify readiness-related behavior

**Files:**
- No additional production files expected.

**Step 1: Run targeted suites**
- Run: `python3 -m pytest -q -p no:cov -o addopts='' tests/runtime/test_contract_compiler.py -k 'release_surface_drift or release_surface_manifest or readiness'`
- Run: `python3 -m pytest -q -p no:cov -o addopts='' tests/scripts/test_github_workflows.py -k release_readiness`

**Step 2: Inspect resulting diff**
- Run: `git diff --stat`
