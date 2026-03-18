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
