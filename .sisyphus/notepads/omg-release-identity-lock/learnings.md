# Learnings — omg-release-identity-lock

## [2026-03-09] Session Init

### Canonical Version Source
- `runtime/adoption.py:14` — `CANONICAL_VERSION = "2.1.1"` — ONLY authored version constant
- No second authored version constant anywhere (shell, JS, YAML, docs, tests)

### Key File Locations
- Drift gate: `runtime/contract_compiler.py:1439` (`_check_version_identity_drift()`)
- Release readiness: `runtime/contract_compiler.py:1733` (`build_release_readiness()`)
- Existing tests: `tests/test_trust_release_identity.py`, `tests/runtime/test_contract_compiler.py`
- E2E tests: `tests/e2e/test_setup_script.py`, `tests/e2e/test_omg_hud.py`

### Known Blind Spots in Existing Drift Gate
- `_check_version_identity_drift()` only checks top-level `marketplace.json` version — MISSES nested fields at lines 9 and 17
- `pyproject.toml` parser uses fragile `line.split('"')[1]` — breaks on single quotes, inline comments, alternate formatting
- `CLI-ADAPTER-MAP.md` must NOT be a runtime blocker — pytest-only enforcement

### Stale Literals to Remove
- `OMG-setup.sh:8` — `VERSION="2.1.1"` hard-coded
- `hud/omg-hud.mjs:90` — static fallback `"2.1.1"`
- `.claude-plugin/scripts/install.sh:22` — banner `v2.1.0` stale

### Tracked Surfaces for sync-release-identity.py
- `package.json`, `pyproject.toml`, `settings.json`
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (ALL 3 fields: lines 9, 17, 35)
- `plugins/core/plugin.json`, `plugins/advanced/plugin.json`
- `registry/omg-capability.schema.json`, `registry/bundles/*.yaml` (23 files)
- `CHANGELOG.md` latest released header

### CI Workflows
- `.github/workflows/omg-release-readiness.yml`
- `.github/workflows/omg-compat-gate.yml`
- `.github/workflows/publish-npm.yml` — NO pip install allowed, use AST extraction

### TDD Policy
- Tests FIRST (RED), then implementation — mandatory for this plan
- Evidence files go in `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## [2026-03-09] Task 2: Canonical Version Extractor

### Implementation Details
- **File**: `scripts/print-canonical-version.py` — zero-dependency AST-based extractor
- **Approach**: Uses Python's `ast` module to parse `runtime/adoption.py` without importing it
- **Output**: Plain semver string (e.g. "2.1.1") with trailing newline, no extra logging
- **Exit codes**: 0 on success, non-zero on parse failure (missing file, syntax error, constant not found)
- **Path resolution**: Dual strategy — tries script location first, falls back to CWD for test isolation

### AST Parsing Strategy
- Walks the AST looking for `ast.Assign` nodes with target `CANONICAL_VERSION`
- Handles both Python 3.8+ (`ast.Constant`) and Python 3.7 (`ast.Str`) for compatibility
- Returns `None` gracefully on any parse failure (missing file, syntax error, constant not found)
- Type-safe: uses `cast()` to satisfy type checker after `isinstance()` guards

### Test Coverage
- **Success path**: Verifies output matches "2.1.1" with correct format (trailing newline, no extra output)
- **Failure paths**: AST extraction returns None for missing file, syntax errors, missing constant
- **7 tests total**: 3 subprocess tests (script behavior) + 4 unit tests (AST extraction)
- **All tests passing**: Verified with pytest

### Evidence Captured
- `.sisyphus/evidence/task-2-canonical-version.txt` — script output ("2.1.1\n")
- `.sisyphus/evidence/task-2-canonical-version-tests.txt` — full pytest output (7 passed)

### Key Design Decisions
1. **AST parsing required** — grep/regex breaks on formatting changes; AST is stable
2. **Zero dependencies** — no `pip install`, no optional imports — works in GitHub Actions
3. **Dual path resolution** — supports both normal execution (from repo root) and test isolation
4. **Graceful failure** — returns None on any error, script exits with code 1 and stderr message
5. **Type safety** — uses `cast()` to handle AST node type complexity

### Integration Points
- Will be used by `scripts/sync-release-identity.py` (Task 3) to read canonical version
- Will be used by `.github/workflows/publish-npm.yml` (Task 6) to compare tag vs canonical vs package.json
- Can be called from shell/bash in CI workflows without pip install

## [2026-03-09] Task 1: Release Identity Regression Tests (TDD RED)

### Tests Added
- `test_trust_release_identity.py`: 4 new tests (runtime consumers, install.sh, compat contract, CLI-ADAPTER-MAP)
- `test_contract_compiler.py`: 2 new tests (marketplace nested drift, malformed pyproject.toml) + `_setup_drift_fixture` helper

### Test Results: 44 passed, 4 xfailed
- **Passing**: runtime consumers (setup.sh + hud.mjs), malformed pyproject.toml parse blocker
- **xfail (strict)**: marketplace nested drift blind spot, stale install.sh v2.1.0, stale OMG_COMPAT_CONTRACT.md v2.1.0, stale CLI-ADAPTER-MAP.md v2.1.0

### Key Findings
- `_check_version_identity_drift()` only checks `["version"]` path for marketplace.json — nested `["metadata", "version"]` and `plugins[0].version` are invisible to the gate
- Malformed pyproject.toml (single quotes) correctly produces explicit `"failed to parse"` blocker via IndexError catch — NOT a silent mismatch
- `OMG-setup.sh` VERSION and `hud/omg-hud.mjs` fallback are both at correct `2.1.1` — only `install.sh` banner is stale
- Fixed pre-existing LSP errors: changed `_load_json` return type from `dict[str, object]` to `dict[str, Any]`
- xfail(strict=True) used to prevent stale markers: tests will error if fixed without removing xfail

### Evidence
- `.sisyphus/evidence/task-1-release-identity-red.txt` — baseline before tests (42 passed)
- `.sisyphus/evidence/task-1-release-identity-tests.txt` — after tests (44 passed, 4 xfailed)

## [2026-03-09] Task 5: Harden Version Drift Gate

### Changes Made
- **`runtime/contract_compiler.py`**: Expanded `_check_version_identity_drift()` with 3-tuple entries (file_path, json_path, label)
- Added marketplace.json nested field checks: `metadata.version` and `plugins[0].version`
- JSON path navigation now handles list indices via `isinstance(current, (list, tuple))` guard
- pyproject.toml parser hardened: explicit `len(parts) >= 2` check before indexing, produces `"failed to parse version (malformed format)"` blocker instead of relying on IndexError
- Removed `xfail(strict=True)` from `test_version_drift_blocker_on_marketplace_nested_version_fields`

### Blocker Format for New Checks
- `"version_drift: marketplace.json metadata.version has version X, expected Y"`
- `"version_drift: marketplace.json plugins[0].version has version X, expected Y"`
- `"version_drift: pyproject.toml: failed to parse version (malformed format)"`
- Existing blocker messages unchanged (display_name falls back to file_path when label is None)

### Type Safety
- Added `list[str | int]` type for json_path to satisfy basedpyright (int keys for list indices)
- Added `isinstance(key, str)` guard in dict branch to narrow `str | int` union for `.get()` call

### Test Results
- 17/17 passed (0 xfailed) — all drift, readiness, marketplace, and pyproject tests green
- `CLI-ADAPTER-MAP.md` remains NOT a runtime blocker (test-only)
- `build_release_readiness()` unchanged — no weakening of existing checks

### Evidence
- `.sisyphus/evidence/task-5-release-gate-error.txt` — pytest output (17 passed)
- `.sisyphus/evidence/task-5-release-gate.json` — release readiness gate output (sha mismatches are pre-existing stale artifacts, not drift)

## [2026-03-09] Task 4: Runtime Consumer Version Fix

### Changes Made
- `.claude-plugin/scripts/install.sh:22` — banner updated from `v2.1.0` to `v2.1.1`
- `tests/test_trust_release_identity.py` — removed `xfail` marker from `test_runtime_consumer_install_sh_version`

### Verification
- `OMG-setup.sh:8` — `VERSION="2.1.1"` already correct, no change needed
- `hud/omg-hud.mjs:90` — static fallback `"2.1.1"` already correct, no change needed
- `test_runtime_consumer_install_sh_version` — now PASSES (was xfail strict)
- All 23 HUD E2E tests pass
- HUD fallback/version tests (3 selected): all pass

### Evidence
- `.sisyphus/evidence/task-4-runtime-consumers.txt` — E2E test run (14 dots + 23 HUD tests)
- `.sisyphus/evidence/task-4-runtime-consumers-error.txt` — HUD fallback/version tests (3 passed)

### Key Decisions
- Updated install.sh to static `v2.1.1` (not dynamic derivation) — this file is tracked by `sync-release-identity.py` going forward
- Removed xfail marker immediately after fix — test is now a live regression guard
- Did NOT change OMG-setup.sh or hud/omg-hud.mjs (already correct per Task 1 findings)

## [2026-03-09] Task 3: Sync/Check Flow for Identity Surfaces

### Implementation
- **File**: `scripts/sync-release-identity.py` — zero-dependency AST-based sync/check tool
- **Modes**: `--check` (exits non-zero on drift, prints drift report) / default write (updates all surfaces)
- **Version source**: Reads `CANONICAL_VERSION` from `runtime/adoption.py` via AST (same logic as `print-canonical-version.py`)

### Tracked Surfaces (35 total fields)
- **JSON (12 fields)**: package.json, settings.json (2 fields: `_omg._version`, `_omg.generated.contract_version`), .claude-plugin/plugin.json, .claude-plugin/marketplace.json (3 fields: top-level, metadata, plugins[0]), plugins/core/plugin.json, plugins/advanced/plugin.json, registry/omg-capability.schema.json
- **Regex (1 field)**: pyproject.toml (`^version = "..."`)
- **YAML (22 files)**: registry/bundles/*.yaml (`^version: ...` line replacement)
- **CHANGELOG (1 field)**: CHANGELOG.md first `## X.Y.Z` header (preserves bracket style and date suffix)

### Key Design Decisions
1. JSON files: `json.load`/`json.dump` with `indent=2` — groups operations per file (load once, update all fields, save once)
2. YAML bundles: regex line replacement (`^version: .*$`) — avoids YAML library reformatting
3. pyproject.toml: regex line replacement (`^version = "..."`) — avoids TOML library dependency
4. CHANGELOG: regex with 3 capture groups to preserve bracket style and date suffix
5. marketplace.json: handles ALL THREE version fields via KeyPath with int indices for list access
6. Nested dict/list navigation: `_get_nested`/`_set_nested` handle both str (dict) and int (list) keys

### Bundle Count
- Task spec said 23 YAML bundles but actual count is 22 — no discrepancy in the code (uses glob)

### Test Results
- `--check` mode: exit 0 when all surfaces in sync
- Drift detection verified: temporarily broke package.json → reported drift with exit 1
- Write mode verified: fixed drift → subsequent `--check` passed
- Test suite: 46 passed, 2 xfailed (strict xfails from Task 1, awaiting later tasks)

### Evidence
- `.sisyphus/evidence/task-3-sync-check.txt` — `--check` output (all in sync)
- `.sisyphus/evidence/task-3-sync-check-error.txt` — pytest output (4 passed, 2 xfailed)

## [2026-03-09] Task 6: Wire CI, Publish, Release to Canonical Identity Checks

### Changes Made
- **`publish-npm.yml`**: Added "Verify canonical version parity" step between existing 2-way tag/package check and npm publish. 3-way comparison: git tag, package.json, `python3 scripts/print-canonical-version.py`. No pip install — script is zero-dependency, python3 available on ubuntu-latest by default.
- **`omg-release-readiness.yml`**: Added "Verify canonical release identity" step (`sync-release-identity.py --check`) after pip install, before artifact regeneration. Artifact regeneration order already matched prescribed sequence (mkdir, doctor, prepare, validate, compile public, compile enterprise, readiness) — no reordering needed.
- **`omg-compat-gate.yml`**: Added "Verify canonical release identity" step (`sync-release-identity.py --check`) after pip install, before compat gate steps.
- **`docs/release-checklist.md`**: Added `sync-release-identity.py --check` as first item in Verification section.

### Key Design Decisions
1. **publish-npm.yml uses print-canonical-version.py** (not sync-release-identity.py) — the print script is purely zero-dependency (ast only), while sync-release-identity reads many files. For tag-gated publish, 3-way tag/package/canonical comparison is sufficient and minimal.
2. **release-readiness and compat-gate use sync-release-identity.py --check** — full 35-field drift check is appropriate since pip install .[test] already runs, providing the broader check surface.
3. **Steps ADD-only** — existing steps unchanged per MUST NOT rules. New steps inserted before existing gates.
4. **Early gating** — identity checks run right after dependency install, before artifact regeneration. If versions drift, fail fast instead of wasting CI time on artifact builds.

### Test Results
- `test_omg_cli.py` + `test_trust_release_identity.py`: 31 passed, 2 xfailed
- publish/release_identity/readiness filter: 26 passed, 2 xfailed

### Evidence
- `.sisyphus/evidence/task-6-workflow-parity.txt` — targeted test run (31 passed, 2 xfailed)
- `.sisyphus/evidence/task-6-workflow-parity-error.txt` — publish/readiness filter (26 passed, 2 xfailed)

## Task 7: Artifact Refresh
- Successfully regenerated all release artifacts using the canonical pipeline.
- Verified that `OMG_COMPAT_CONTRACT.md` version is correctly updated to `2.1.1` via regeneration.
- Updated `CLI-ADAPTER-MAP.md` version example to match `CANONICAL_VERSION`.
- Removed xfail markers from `tests/test_trust_release_identity.py` and verified all tests pass.
- The 6-step regeneration pipeline is essential for maintaining artifact consistency.

## [2026-03-09] Plan compliance audit rerun

### Audit findings
- `scripts/print-canonical-version.py` prints `2.1.1` and `scripts/sync-release-identity.py --check` reports all tracked surfaces in sync.
- Targeted pytest gate is green: `55 passed` across release identity, contract compiler, and canonical version extractor coverage.
- `CLI-ADAPTER-MAP.md` now has 0 remaining `2.1.0` matches; `tests/scripts/test_print_canonical_version.py` imports `CANONICAL_VERSION` for output assertions.

## [2026-03-09] Task 1 (Plan 2): Shared Release Surface Inventory

### Implementation
- **runtime/release_surfaces.py** — pure data module, no runtime.adoption imports (avoids circular deps)
- **AuthoredSurface** — frozen dataclass: `file_path`, `surface_type`, `field`, `description`
- **SURFACE_TYPES** — frozenset of 8 valid types: json_key_path, regex_line, yaml_line, frontmatter_field, changelog_header, shell_literal, js_literal, banner_literal

### Inventory Counts
- **42 total AUTHORED_SURFACES entries**: 10 JSON key paths + 1 regex (pyproject) + 22 YAML bundles + 1 changelog + 1 frontmatter + 3 CLI-ADAPTER-MAP regex + 1 shell + 1 js + 1 banner + 1 json (snapshot)
- **37 unique authored file paths** across all entries
- **3 DERIVED_SURFACE_DIRS**: dist/, artifacts/release/, build/lib/
- **6 SCOPED_RESIDUE_TARGETS**: dist manifests, bundles, artifacts, build

### 6 Previously Missing Surfaces Now Tracked
1. OMG_COMPAT_CONTRACT.md → frontmatter_field "version"
2. CLI-ADAPTER-MAP.md → 3 regex_line entries (badge, JSON literal, Python constant)
3. OMG-setup.sh → shell_literal VERSION="..."
4. hud/omg-hud.mjs → js_literal return "X.Y.Z"
5. .claude-plugin/scripts/install.sh → banner_literal vX.Y.Z
6. runtime/omg_compat_contract_snapshot.json → json_key_path ["contract_version"]

### Bundle Count
- Confirmed 22 YAML bundles (explicitly listed, not glob-discovered)

### Test Coverage (27 tests)
- Completeness: total count, JSON surfaces, YAML bundles, 6 missing, pyproject, changelog
- Type safety: valid surface types, json fields are lists, regex fields are strings, descriptions present
- Disk existence: all 37 paths verified on disk
- Helpers: get_authored_paths uniqueness and count, get_derived_dirs
- Negative: bogus path rejection, frozen immutability, no duplicate entries

### Evidence
- `.sisyphus/evidence/task-1-release-surface-inventory.txt` — 27 passed
- `.sisyphus/evidence/task-1-release-surface-inventory-error.txt` — 2 passed (negative tests)

## [2026-03-09] Task 2 (Plan 2): Refactor sync-release-identity.py to shared inventory

### Implementation
- **Removed**: `JSON_SURFACES`, `REGEX_SURFACES`, `YAML_BUNDLE_DIR`, `CHANGELOG_FILE` hardcoded constants
- **Added**: `from runtime.release_surfaces import AUTHORED_SURFACES, DERIVED_SURFACE_DIRS, AuthoredSurface`
- **Dispatch pattern**: `_CHECK_DISPATCH` and `_UPDATE_DISPATCH` dicts map surface_type → handler function
- **Public API**: `check_surface(repo_root, surface, canonical)` and `update_surface(repo_root, surface, canonical)`

### New handlers
- `frontmatter_field`: regex match between `---` delimiters, update named YAML field
- `shell_literal`, `js_literal`, `banner_literal`: all use same generic `_check_regex`/`_update_regex` handler
- `_replace_group1(m, new_version)` — replaces captured group 1 preserving surrounding text (prefix/suffix slicing)

### Derived directory guard
- `_guard_derived()` raises `ValueError` if surface.file_path starts with any `DERIVED_SURFACE_DIRS` entry
- Applied in both `check_surface` and `update_surface` (fail-fast)

### Type safety
- `surface.field` is `Union[list[str|int], str]` — each handler uses `cast()` to narrow
- LSP clean (0 errors on basedpyright)

### Test coverage (33 tests)
- 5 shared inventory tests (no hardcoded constants, import present)
- 3 derived directory guard tests (inventory check, update refuses, check refuses)
- 12 new handler tests (3 each: frontmatter, shell, js, banner — check drift, check no drift, update)
- 9 existing handler tests (json, regex, yaml, changelog — check + update)
- 2 drift reporting tests (correct current version in output)
- 2 integration tests (subprocess --check exits 0, output mentions "in sync")

### Evidence
- `.sisyphus/evidence/task-2-authored-sync.txt` — --check exits 0, all in sync
- `.sisyphus/evidence/task-2-authored-sync-error.txt` — 18 drift-related tests passed

## Task 3: validate-release-identity.py

### Patterns
- `importlib.util` for loading hyphenated scripts as modules — must assert `spec is not None and spec.loader is not None` for type narrowing
- `check_surface` from `sync-release-identity.py` reused directly via importlib — no code duplication
- CHANGELOG.md historical entries excluded via `^## \[?\d+\.\d+\.\d+\]?` regex match
- `.sisyphus/` directory is gitignored — evidence files cannot be committed

### Key Design
- Scoped residue scan against real repo finds 130+ hits in `dist/`, `artifacts/release/`, `build/lib/` — all containing current canonical version 2.1.1. This is expected: `--forbid-version` is designed for post-bump validation (forbid the OLD version after bumping to new one)
- Derived validation gracefully skips missing files (generated trees may not exist)
- `build_report()` aggregates all three sections and sets `overall_status` to `fail` if any section has blockers

### Evidence
- `.sisyphus/evidence/task-3-release-identity-validator.json` — full JSON output with scoped_residue blockers
- `.sisyphus/evidence/task-3-release-identity-validator-error.txt` — 8 drift/mismatch/residue tests passed

## Task 4 — Regression test expansion (2026-03-09)

- `_setup_drift_fixture()` in test_contract_compiler.py expects parent dirs pre-created — must `mkdir(parents=True)` first
- `.sisyphus/` is gitignored — use `git add -f` for evidence files
- `test_validate_release_identity.py` has NO `single_surface` test — the `-k single_surface` filter deselects all 15 tests
- `build_release_readiness()` stores drift check at `checks["version_identity_drift"]` with `status`, `blockers`, `canonical_version`, `drift_details`
- `_check_version_identity_drift(root)` is the underlying function; accepts a Path root for fixture-based testing
- Tests added: 5 new tests in `test_trust_release_identity.py` (inventory-driven existence, 3 specific version assertions, surface coverage spot-check)
- Tests added: 2 new tests in `test_contract_compiler.py` (drift section presence, drift section blocker on mismatch)
- Total suite: 132 tests pass across all 5 targeted files
- Task 5: scripts/omg.py contract validate now embeds a release_identity report from validate-release-identity.py and exits non-zero when release_identity.overall_status is fail.\n- Task 5: runtime.contract_compiler._check_version_identity_drift now uses AUTHORED_SURFACES plus check_surface from scripts/sync-release-identity.py, removing duplicate hardcoded drift surface logic while preserving blocker format.\n- Task 5: Added machine-readable contract-validate tests for release_identity sections and blocker payloads, and aligned malformed pyproject expectation with shared check_surface output (<pattern not found>).\n- Task 5 follow-up: release_identity output in contract validate is now machine-readable and gate-enforced with non-zero exit on validator failure.
- Task 5 follow-up: version drift gate now reuses authored surface inventory through shared check_surface logic to avoid duplicated drift lists.
- Task 5 follow-up: runtime contract compiler tests now assert release_identity blocker payload sections and scoped residue payload fields.

## [2026-03-09] Task 6: Final Release Identity Validator Integration

### Changes Made
- **.github/workflows/omg-release-readiness.yml**: Added `validate-release-identity.py --scope all --forbid-version 2.1.1` after standalone verification.
- **.github/workflows/omg-compat-gate.yml**: Added the same validator step after regression tests.
- **.github/workflows/publish-npm.yml**: Added both the identity validator and `omg.py contract validate` before `npm publish`.
- **scripts/verify-standalone.sh**: Added the identity validator call to the verification sequence.
- **docs/release-checklist.md**: Updated Verification section with explicit sync and validation steps.

### Key Design Decisions
1. **Late-stage validation**: The full identity validator runs after artifact generation and standalone verification to ensure that generated residue (dist/, artifacts/) is also checked for forbidden versions.
2. **Contract validation in publish**: Added `omg.py contract validate` to the publish workflow as a final safety gate for the contract registry.
3. **Checklist parity**: The release checklist now mirrors the CI gates, allowing for manual verification that matches automated enforcement.

### Verification
- `python3 -m pytest tests/scripts/test_omg_cli.py tests/test_trust_release_identity.py -k "validate or readiness or publish" -q` passed (3 tests).
- Manual execution of `scripts/validate-release-identity.py --scope all --forbid-version 2.1.1` confirmed it correctly identifies residue in `dist/`, `artifacts/`, and `build/`.

### Evidence
- `.sisyphus/evidence/task-6-workflow-parity.txt` — pytest output (3 passed).
