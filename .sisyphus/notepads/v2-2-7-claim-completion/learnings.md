# Task 1: Freeze Canonical Release-Text and Public-Command Contract

## Learnings

- Registry pattern: `PUBLIC_SURFACES` list of dicts with `id`, `category`, `path`, `description` keys; `_REQUIRED_IDS` frozenset enforces completeness
- `_REQUIRED_CATEGORIES` must include any new category (added `release_body` for GitHub/tag body artifacts)
- `GENERATED_SECTION_MARKERS` maps logical names to HTML comment markers for idempotent doc section insertion
- `validate_registry()` is the single validation entrypoint — extended with `/OMG:crazy` exclusion check on `PROMOTED_PUBLIC_COMMANDS`
- TDD approach: import-level failure confirmed tests fail before implementation (ImportError on missing `PROMOTED_PUBLIC_COMMANDS`)
- Curated `PROMOTED_PUBLIC_COMMANDS` list is the authoritative source for public docs promotion — argparse extraction remains a validator only
- Minimum surface count bumped from 23 to 26 to account for 3 new surfaces
- Compiler tests import directly from registry to verify cross-module contract
- All 64 tests pass, 0 LSP errors on all 3 changed files

## Files Changed
- `runtime/release_surface_registry.py` — new surfaces, marker, curated commands, validation
- `tests/scripts/test_release_surface_registry.py` — TDD tests for new contract
- `tests/runtime/test_release_surface_compiler.py` — compiler-side contract tests

# Task 2: Unified Release Text and Check-Only Compiler Mode

## Learnings

- `_compile_release_text(version)` is the single canonical builder; returns markdown snippet with version header and 3 bullet items
- Old `_changelog_content()` and `_write_release_notes()` were independent generators with divergent content ("manifests" vs "artifact output") — replaced by shared builder
- Four outputs derive from `_compile_release_text()`: changelog marker block, release notes artifact, release body artifact, tag body artifact
- Artifact content builders (`_release_notes_content`, `_release_body_content`, `_tag_body_content`) wrap the canonical text with appropriate document structure
- `check_only=True` mode does read-only drift detection: extracts marker content via regex, compares artifacts byte-for-byte, returns named `drift` list
- `_extract_marker_content()` uses `re.DOTALL` regex matching `open_tag\n(.*?)\nclose_tag` to precisely extract section body
- Marker drift and artifact drift are separate check functions allowing granular diagnostics per surface
- TDD confirmed: ImportError on `_compile_release_text` verified red phase before implementation
- 110 total tests pass (27 matched by task filter), 0 LSP errors on both changed files
- `_upsert_section()` mechanism preserved unchanged — check mode compares against its output format

## Files Changed
- `runtime/release_surface_compiler.py` — unified text builder, check_only mode, release body + tag body artifacts
- `tests/runtime/test_release_surface_compiler.py` — 10 new tests for unified text, check mode, artifact creation

# Task 4: Regenerate Public Front Door Around omg Launcher

## Learnings

- `_quickstart_content()` is the single source for the README quickstart generated block — changing it automatically flows through `_upsert_section` and `_check_release_surfaces` drift detection
- `_command_surface_snippet()` was argparse-based (AST extraction from `scripts/omg.py`); switched to `get_promoted_public_commands()` from registry — decouples docs from parser internals
- New `_proof_content()` wired into both `compile_release_surfaces()` (write path) and `_check_release_surfaces()` (drift check) via `proof_generated_section` marker from registry
- `/OMG:crazy` appears only as `> Compatibility:` blockquote footnote in generated quickstart — test enforces footnote-only context via keyword check (`compat`, `footnote`, `legacy`, `alias`, `>`)
- Node >=18 prerequisite uses markdown blockquote banner: `> **Prerequisite**: Node >=18`
- `_write_command_surface_doc()` intentionally kept using `_extract_commands()` for the full reference doc — only the README snippet uses promoted commands
- Existing drift detection test updated: tamper string changed from `npm install @trac3er/oh-my-god` to `omg install --plan` to match new content
- TDD red phase confirmed via ImportError on `_proof_content` before implementation
- 40 total tests pass (17 matched by task filter), 0 LSP errors on both changed files

## Files Changed
- `runtime/release_surface_compiler.py` — updated 4 functions, added `_proof_content()`, wired proof into compile + check paths
- `tests/runtime/test_release_surface_compiler.py` — 17 new tests across 4 test classes (TestQuickstartContent, TestInstallFastPathContent, TestProofContent, TestCommandSurfaceSnippet)

# Task 5: Extend docs generate --check to Cover All Generated Artifacts

## Learnings

- `.sisyphus/tmp/generated-docs/` is gitignored — artifacts there can't be verified by CI `--check`; solution: copy all 9 to ROOT_DIR on `docs generate`
- `GENERATED_ARTIFACTS` tuple in `doc_generator.py` is the single source of truth for artifact names; used by both `generate_docs()` return value and `check_docs()`
- `check_docs(on_disk_root)` generates fresh to tempdir, compares all 9 against `on_disk_root`; JSON comparison strips `generated_at` timestamps; malformed JSON on disk treated as drift
- `cmd_docs_generate --check` now delegates to `check_docs(ROOT_DIR)` instead of inline 2-file comparison
- `cmd_docs_generate` write mode expanded from copying 2 root docs to copying all 9 artifacts to ROOT_DIR
- Content fixes: install-verification.json commands changed from `python3 scripts/omg.py doctor/validate` to `omg doctor/validate`; QUICK-REFERENCE.md Quick Commands changed from `/OMG:setup`, `/OMG:crazy`, `/OMG:browser`, `/OMG:deep-plan` to `omg install --plan`, `omg doctor`, `omg ship`
- TDD red phase confirmed via ImportError on `check_docs` and `GENERATED_ARTIFACTS` before implementation
- 34 total tests pass (17 doc_generator + 17 github_workflows), 0 LSP errors on all 3 changed files

## Files Changed
- `runtime/doc_generator.py` — added `GENERATED_ARTIFACTS`, `check_docs()`, fixed content in install-verification.json and QUICK-REFERENCE.md
- `scripts/omg.py` — updated import, rewrote `cmd_docs_generate` check/write modes
- `tests/runtime/test_doc_generator.py` — 8 new tests for check_docs and content verification
- Root artifacts regenerated: all 9 at ROOT_DIR

# Task 3: Move Release/Docs Drift Checking Ahead of Artifact Compilation in CI

## Learnings

- `_check_release_surface_drift(root, output_root)` extended with two new calls: `compile_release_surfaces(root, check_only=True)` and `check_docs(root)` — drift items prefixed with `release_text_drift:` and `docs_drift:` respectively
- Both new imports added at module level in `contract_compiler.py`: `from runtime.release_surface_compiler import compile_release_surfaces` and `from runtime.doc_generator import check_docs`
- `compile_release_surfaces` drift items are dicts with `surface`, `path`, `reason` keys — formatted as `{surface}: {reason}` in blocker string
- `check_docs` drift items are plain strings (e.g. `"Missing: support-matrix.json"`) — used directly in blocker string
- Existing fixture tests (`_build_surface_drift_fixture`) needed monkeypatch stubs for both new calls since fixture roots don't contain all doc/release artifacts — extracted `_stub_release_text_and_docs_clean(monkeypatch)` helper
- Workflow change: "Compile release surfaces into output root" (self-healing step in `release-readiness` job) replaced with "Check release and docs drift (repo root)" that runs read-only `check_only=True` against `Path('.')`
- Self-healing compile step was removed from `release-readiness` because compilation now happens in `compile-public` and `compile-enterprise` jobs
- TDD red phase: 7 tests failed (AttributeError on missing imports + missing workflow step); green phase: all 112 tests pass
- 0 LSP errors on all 4 changed files

## Files Changed
- `runtime/contract_compiler.py` — added imports, extended `_check_release_surface_drift()` with release-text and docs drift blockers
- `.github/workflows/omg-release-readiness.yml` — replaced self-healing compile step with read-only drift check step
- `tests/runtime/test_contract_compiler.py` — 7 new tests, updated 5 existing fixture tests with monkeypatch stubs
- `tests/scripts/test_github_workflows.py` — 2 new workflow invariant tests

# Task 6: Add Env-Doctor Pack and `omg env doctor` Alias

## Learnings

- `_doctor_check()` returns `{name, status, message, required}` — env doctor needed `remediation` field so created `_env_check()` helper with extended schema
- `_ENV_HOST_CONFIG_DIRS` maps host names to home-relative config directory parts; reuses `OMG_TEST_HOME_DIR` env var for test isolation (same pattern as orphaned_runtime tests)
- Provider auto-registration requires explicit imports: `import runtime.providers.codex_provider` etc. before calling `get_provider()` — providers register themselves on import via `register_provider()`
- `check_auth()` returns `tuple[bool | None, str]` — `True/False/None` tri-state; env doctor maps `None` to warning status
- Claude auth is special-cased as `host-native/non-probed` with `status=ok` — no subprocess probe, always participates in PATH/config-dir checks
- All env checks use `required=False` — env pack is advisory, never blocks release-readiness doctor
- `_infer_repair_pack()` in `omg.py` handles `repair_pack` assignment post-hoc; env checks get pack inference from name keywords
- Parser structure: `env` -> subparser `doctor` with `--format` flag, mirrors `cmd_doctor()` text output style
- Node version check: runs `node --version`, strips `v` prefix, parses major int, compares `>= 18`
- Config dir writability: checks `os.access(target, os.W_OK)` if dir exists, falls back to parent writable check
- TDD red phase: ImportError on `run_env_doctor` confirmed before implementation
- 42 tests pass (14 new: 10 unit + 4 CLI), 0 LSP errors on all 4 changed files

## Files Changed
- `runtime/compat.py` — added `run_env_doctor()`, `_env_check()`, `_check_node_version()`, `_check_python3_available()`, `_check_cli_path()`, `_check_cli_auth()`, `_check_writable_config_dir()`, `_ENV_HOST_CLIS`, `_ENV_HOST_CONFIG_DIRS`
- `scripts/omg.py` — added `cmd_env_doctor()`, `omg env doctor` subparser, imported `run_env_doctor`
- `tests/runtime/test_compat_doctor.py` — 10 new tests in `TestEnvDoctor` class
- `tests/scripts/test_omg_cli.py` — 4 new CLI tests for `omg env doctor`

# Task 7: Require Env Preflight Before Install Plan/Apply

## Learnings

- `_run_install_preflight()` wraps `run_env_doctor()` with `OMG_TEST_PREFLIGHT_BLOCK` env var for subprocess-safe test injection — monkeypatch can't affect forked subprocess, so env var is the test seam
- Blocking logic: `status == "blocker"` AND `required == True` — currently all env checks have `required=False`, so install won't block in practice until a check is promoted
- `preflight_inject` dict uses `**` splat into each output dict (`plan_data`, `apply_data`, `result_data`) to add `preflight` key only when relevant
- `--skip-preflight` returns `{"preflight": {"skipped": true}}` — distinct from absent (dry-run path) or present (plan/apply path)
- Human-readable output: `_format_preflight_text()` prints before install plan output, with `[OK]`/`[WARNING]`/`[BLOCKER]` tags per check
- Blocked path emits structured JSON with `schema` matching the expected output type (InstallPlan or InstallApplyResult) plus `preflight` key
- TDD red phase confirmed: `assert "preflight" in out` failed before implementation
- 12 tests pass (8 new + 4 env doctor), 0 LSP errors on both changed files

## Files Changed
- `scripts/omg.py` — added `_run_install_preflight()`, `_format_preflight_text()`, `--skip-preflight` flag, preflight gating in `cmd_install()`
- `tests/scripts/test_omg_cli.py` — 8 new tests for install preflight gating
