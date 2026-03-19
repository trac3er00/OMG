# Release Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a shared release-audit engine, expose it as `omg release audit --artifact`, block `omg ship` on drift, and support guarded GitHub release remediation.

**Architecture:** Centralize release audit logic in `runtime/release_artifact_audit.py`, reuse it from the standalone artifact audit script, and hang the operator-facing workflow off `scripts/omg.py`. Treat local artifact checks and remote GitHub checks as one report so the apply path can show a precise mutation diff before making any API changes.

**Tech Stack:** Python 3.10+, argparse, stdlib HTTP/JSON/tarfile/tempfile, pytest, existing OMG release-surface tooling.

---

### Task 1: Shared engine skeleton

**Files:**
- Create: `runtime/release_artifact_audit.py`
- Modify: `tests/scripts/test_audit_published_artifact.py`
- Create: `tests/runtime/test_release_artifact_audit.py`

**Step 1: Write the failing test**
- Add a test proving the new shared engine can audit a source tree and reports required sections.

**Step 2: Run test to verify it fails**
- Run: `python3 -m pytest tests/runtime/test_release_artifact_audit.py -q`
- Expected: FAIL because the module/functions do not exist yet.

**Step 3: Write minimal implementation**
- Add the shared engine with typed report-building helpers and source-tree checks moved out of `scripts/audit-published-artifact.py`.

**Step 4: Run test to verify it passes**
- Run: `python3 -m pytest tests/runtime/test_release_artifact_audit.py tests/scripts/test_audit_published_artifact.py -q`

### Task 2: CLI and ship gate

**Files:**
- Modify: `scripts/omg.py`
- Modify: `tests/scripts/test_release_audit_cli.py`
- Modify: `tests/runtime/test_release_artifact_audit.py`

**Step 1: Write the failing test**
- Add CLI tests for `omg release audit --artifact` dry-run output and a ship-gate test that fails on drift.

**Step 2: Run test to verify it fails**
- Run: `python3 -m pytest tests/scripts/test_release_audit_cli.py -q`

**Step 3: Write minimal implementation**
- Add the release audit subcommand and call the shared engine from `cmd_ship`.

**Step 4: Run test to verify it passes**
- Run: `python3 -m pytest tests/scripts/test_release_audit_cli.py -q`

### Task 3: GitHub apply path

**Files:**
- Modify: `runtime/release_artifact_audit.py`
- Modify: `tests/runtime/test_release_artifact_audit.py`

**Step 1: Write the failing test**
- Add mocked GitHub API tests for missing-release creation, latest-sync updates, asset upload planning, and confirmation/credential gating.

**Step 2: Run test to verify it fails**
- Run: `python3 -m pytest tests/runtime/test_release_artifact_audit.py -q`

**Step 3: Write minimal implementation**
- Add the guarded `--apply` flow with rollback journal output and API mutation helpers.

**Step 4: Run test to verify it passes**
- Run: `python3 -m pytest tests/runtime/test_release_artifact_audit.py -q`

### Task 4: Docs and workflow surfaces

**Files:**
- Modify: `runtime/doc_generator.py`
- Modify: `README.md`
- Modify: `docs/command-surface.md`
- Modify: `QUICK-REFERENCE.md`
- Modify: `.github/workflows/release.yml`
- Modify: tests covering docs/workflows as needed

**Step 1: Write the failing test**
- Add coverage ensuring the new command is present in docs/help surfaces and release readiness runs it.

**Step 2: Run test to verify it fails**
- Run: `python3 -m pytest tests/scripts/test_github_workflows.py tests/runtime/test_doc_generator.py tests/runtime/test_release_surface_compiler.py -q`

**Step 3: Write minimal implementation**
- Update generated docs/help/workflows and keep them packaged.

**Step 4: Run test to verify it passes**
- Run: `python3 -m pytest tests/scripts/test_github_workflows.py tests/runtime/test_doc_generator.py tests/runtime/test_release_surface_compiler.py -q`
