# OAL v1.3 Production Hardening Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Lock OMC compatibility as a production-grade contract with versioned snapshots, strict drift gates, and hardened request validation.

**Architecture:** Extend the OMC compatibility layer with explicit contract versioning + migration hooks, add runtime request validation/audit logging, and enforce these constraints via CI gates and no-vendor verification.

**Tech Stack:** Python 3.12, pytest, GitHub Actions.

---

### Task 1: Contract Versioning + Migration Hooks

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/runtime/omc_compat.py`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/scripts/oal.py`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/runtime/omc_contract_snapshot.json`
- Test: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/runtime/test_omc_contract_snapshot.py`

**Steps:**
1. Add `contract_version` metadata to snapshot payload.
2. Add migration utility stubs for older snapshot schema compatibility.
3. Ensure `oal omc snapshot` emits deterministic payload.
4. Update snapshot test to verify version + schema.

### Task 2: Snapshot Drift Gate

**Files:**
- Create: `/Users/cminseo/Documents/scripts/Shell/OAL/scripts/check-omc-contract-snapshot.py`
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/.github/workflows/omc-compat-gate.yml`
- Test: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/scripts/test_omc_snapshot_check.py`

**Steps:**
1. Add a check script that compares runtime contracts to committed snapshot.
2. Run that check in CI before full tests.
3. Add unit test for script success/failure behavior.

### Task 3: Request Validation + Audit Logging

**Files:**
- Modify: `/Users/cminseo/Documents/scripts/Shell/OAL/runtime/omc_compat.py`
- Test: `/Users/cminseo/Documents/scripts/Shell/OAL/tests/runtime/test_omc_compat.py`

**Steps:**
1. Validate input length/count/path safety in `dispatch_omc_skill`.
2. Add audit ledger writes for every dispatch result.
3. Add tests for invalid input rejection and audit event creation.

### Task 4: Full Verification

**Files:**
- Modify docs if needed: `/Users/cminseo/Documents/scripts/Shell/OAL/README.md`

**Steps:**
1. Run targeted tests for compat/snapshot/CLI.
2. Run full test suite.
3. Run no-vendor verifier script.
4. Confirm CI workflow file and local outputs are consistent.

