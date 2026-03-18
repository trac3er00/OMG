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
