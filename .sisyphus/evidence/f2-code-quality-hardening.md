# F2 — Code Quality Review: `omg-roadmap-hardening`

**Branch:** `feature/omg-roadmap-hardening`  
**Reviewer:** Sisyphus-Junior (automated)  
**Date:** 2026-03-09  

## F2 VERDICT: APPROVE (conditional)

## QUALITY CHECKS

| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | Test suite (runtime) | **PASS** | 133/134 passed. 1 failure is pre-existing (`test_dispatch_all_compat_skills` — Gemini CLI timeout, commit `00c20fe` predates branch) |
| 2 | Test suite (scripts) | **WARN** | 40/41 passed. `test_cli_release_readiness_dual_channel` fails — see MEDIUM findings |
| 3 | Test suite (integration) | **PASS** | 59/59 passed |
| 4 | No duplicated requirement tables | **PASS** | `security_check.py` and `preflight.py` have thin `_requirements_for_profile` wrappers that delegate to `runtime.evidence_requirements` via lazy import. No table duplication. |
| 5 | No second profile store | **PASS** | `validate.py::_check_profile_governor` is a doctor/health-check that reads from the single canonical profile at `.omg/state/profile.yaml`. Not a sidecar. |
| 6 | Fail-closed behavior | **PASS** | `requirements_for_profile(None) == requirements_for_profile('') == requirements_for_profile('unknown')` — all return 9 full requirements |
| 7 | NotebookLM opt-in only | **PASS** | Found in `MCP_CATALOG` with `default: False`, no `min_preset`. Warning text present. |
| 8 | Pre-install integrity before mutation | **PASS** | `verify_install_integrity` at line 1529, `provision_managed_venv` at line 1846. Integrity check runs first. |
| 9 | Test quality — no trivial assertions | **PASS** | New test files have substantive assertion counts: `test_forge_agents`(112), `test_omg_cli`(203), `test_runtime_profile`(47), `test_background_verification`(45), `test_proof_gate`(33). No trivial `assert True` patterns. |
| 10 | No TODO/FIXME in new tests | **PASS** | Only TODO references in test files are (a) test fixture content being analyzed by analyzers, or (b) pre-existing files outside branch scope. |
| 11 | Scope compliance | **PASS** | 66 files changed. All in expected directories: `runtime/`, `hooks/`, `scripts/`, `tests/`, `commands/`, `hud/`, `plugins/`, `OMG-setup.sh`, `pyproject.toml`. Evidence/notepad files in `.sisyphus/`. |

## HIGH-SEVERITY FINDINGS

None.

## MEDIUM-SEVERITY FINDINGS

### M1: `test_cli_release_readiness_dual_channel` fixture gap

**File:** `tests/scripts/test_omg_cli.py:727`  
**Symptom:** `readiness.returncode == 2` (expected 0)  
**Root cause:** The branch expanded readiness checks (execution_primitives, proof_chain_linkage, doctor checks). The `_seed_release_readiness_fixtures()` function was updated in commit `06af096` to include new fields, but the readiness command still reports blockers for missing compiled manifests (`dist/public/manifest.json`, `dist/enterprise/manifest.json`), bundle outputs, and `doctor.json`. The fixtures don't seed all the artifacts the expanded readiness surface now demands.  
**Risk:** Low — this is a test fixture completeness gap, not a production logic bug. The underlying readiness logic correctly detects missing artifacts.  
**Recommendation:** Expand `_seed_release_readiness_fixtures` to also seed `dist/*/manifest.json`, bundle skill outputs, and `.omg/evidence/doctor.json` so the dual-channel readiness test passes end-to-end.

## LOW-SEVERITY FINDINGS

### L1: Lazy-import wrapper duplication pattern

`runtime/security_check.py:215` and `runtime/preflight.py:107` both contain identical `_requirements_for_profile` wrapper functions with the same lazy-import-from-`evidence_requirements` pattern. While not a data duplication issue (they correctly delegate), the identical wrapper could be extracted into a shared utility to reduce maintenance surface.

## SUMMARY

Branch is **structurally sound**. All critical invariants hold:
- Single source of truth for evidence requirements (no table duplication)
- Single profile store (no governor sidecar)
- Fail-closed behavior verified
- NotebookLM correctly gated as opt-in
- Pre-install integrity ordering correct
- Tests are substantive with proper assertion coverage
- Scope is clean

The one failing test (M1) is a fixture gap — the production logic is correct but the test doesn't seed all artifacts the expanded readiness surface requires. This does not block approval but should be addressed before merge.
