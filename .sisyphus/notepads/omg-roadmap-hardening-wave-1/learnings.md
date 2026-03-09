# Learnings — omg-roadmap-hardening-wave-1

## [2026-03-09] Plan initialized
- Plan: `.sisyphus/plans/omg-roadmap-hardening-wave-1.md`
- All 5 tasks unchecked — execution begins with Task 1
- Critical P0 bug: `hooks/session-end-capture.py:327` writes `json.dumps()` to `profile.yaml`; `hooks/setup_wizard.py:694` writes `yaml.safe_dump()` — both read via `yaml.safe_load()` but produce different raw text → divergent `profile_version` SHA256 hashes
- Fix: create `runtime/profile_io.py` as shared canonical read/write module; derive `profile_version` from parsed dict, not raw text
- 5 profile consumers: `context_engine`, `claim_judge`, `evidence_query`, `contract_compiler`, `session-end-capture`
- Missing `evidence_profile` must fail closed to full requirements (never weaken)
- Decay metadata recorded in Task 2 but no preference deletion until review surface exists (Task 3)

## [2026-03-09] Task 1 COMPLETE — fix(profile): canonicalize profile serialization
### Key discoveries
- **LOCAL yaml.py STUB**: The project has a local `yaml.py` at the project root that shadows PyYAML. It has NO `yaml.SafeDumper` class — only `safe_load`, `safe_dump`, `dump`, `load`. Any code using `yaml.SafeDumper` will fail with `AttributeError`.
- **Empty collection bug**: The yaml stub renders empty lists/dicts as bare keys (e.g., `tags:` with no value), which `yaml.safe_load` parses back as `None`. Must post-process with `_render_empty_collections()` to fix known profile fields.
- **`_clean_single_line(None)` returns `"None"`**: In `context_engine._resolve_profile_version_pointer`, calling `_clean_single_line(profile.get("profile_version"))` when the key doesn't exist returns `"None"` (truthy string). Fixed by adding `if candidate is None: continue` guard.
- **Double-write in setup_wizard.py**: `_write_profile_learning_sections` now calls `save_profile` then re-reads and re-writes with `_render_explicit_empty_collections`. This is redundant but harmless since `save_profile` already handles empty collections. Could be simplified in Task 2.
- **profile_version determinism**: `profile_version_from_map` uses `json.dumps(data, sort_keys=True)` → SHA256. This is format-independent (JSON vs YAML raw text doesn't matter).

### Files created/modified
- `runtime/profile_io.py` (NEW): `load_profile()`, `save_profile()`, `profile_version_from_map()`, `_render_empty_collections()`
- `hooks/session-end-capture.py`: migrated read (~213) and write (~327) to use `profile_io`
- `hooks/setup_wizard.py`: migrated `_load_profile_yaml` to use `profile_io.load_profile`
- `runtime/context_engine.py`: fixed `_resolve_profile_version_pointer` None guard + import `profile_version_from_map`
- Tests: 42 tests pass in target suite, 816 total unit tests pass

### Patterns to follow in Task 2
- Always use `profile_io.load_profile()` and `profile_io.save_profile()` for profile reads/writes
- Never use `yaml.SafeDumper` — use `yaml.safe_dump()` only
- Empty collection fields need `_render_empty_collections` post-processing (already in `save_profile`)
- `profile_version_from_map` is the canonical version algorithm — use it everywhere

## [2026-03-09] Task 2 COMPLETE — governed preference schema foundation
- Added  with  and  sections while preserving legacy  for context digest compatibility.
- Learned preference entries now carry governance provenance fields: , , , , .
- Session-end promotion now upserts governed entries and marks destructive signals as  instead of auto-applying to legacy preferences.
- Inferred style preferences now include  (, , ); safety entries remain decay-immune by design (no decay metadata).
-  now classifies each signal into style/safety and surfaces a destructive flag for governance decisions in promotion flow.

### Task 2 correction note
- Added governed_preferences with style and safety sections while preserving legacy preferences for context digest compatibility.
- Learned preference entries now carry governance provenance fields: source, learned_at, updated_at, section, confirmation_state.
- Session-end promotion now upserts governed entries and marks destructive signals as pending_confirmation instead of auto-applying to legacy preferences.
- Inferred style preferences now include decay_metadata (decay_score, last_seen_at, decay_reason); safety entries remain decay-immune by design (no decay metadata).
- runtime/memory_store.py now classifies each signal into style/safety and surfaces a destructive flag for governance decisions in promotion flow.

## [2026-03-09] Task 3 COMPLETE — feat(profile): add review command
- `profile-review` subcommand added to `scripts/omg.py` — read-only, never mutates profile.yaml.
- Default output is `--format json`; `--format text` produces human-readable summary.
- JSON schema: `ProfileReview` with keys: `style`, `safety`, `pending_confirmations`, `decay_candidates`, `provenance_summary`, `profile_version`.
- `ensure_governed_preferences()` called in-memory only — no disk write.
- Registered in `plugins/core/plugin.json` under `observability` category.
- `commands/OMG:profile-review.md` follows `health-check.md` frontmatter pattern.
- Read-only regression test snapshots mtime+content before/after execution.
- 4 new tests, all 32 CLI tests pass.


## [2026-03-09] Task 4 COMPLETE — evidence-profile classifier + requirement registry
- Added additive `evidence_profile` emission in `runtime/delta_classifier.py`; `categories` output remains unchanged.
- Introduced single-source registry in `runtime/evidence_requirements.py` with profiles: `code-change`, `docs-only`, `forge-run`, `security-audit`, `release`.
- Enforced fail-closed resolver behavior: missing/empty/unknown profile returns `FULL_REQUIREMENTS`.
- `docs-only` intentionally carries fewer requirements than `code-change`; `release` and `security-audit` map to full requirement set.
- Updated downstream consumers (`runtime/preflight.py`, `runtime/security_check.py`) to derive `evidence_requirements` from the shared resolver while preserving existing routing behavior.
- Added TDD coverage in `tests/runtime/test_delta_classifier.py` and extended `tests/runtime/test_preflight.py` + `tests/runtime/test_security_check.py` for additive + fail-closed requirements behavior.

## [2026-03-09] Task 5 COMPLETE — profile-aware proof/claim/query/release gates
-  now resolves required artifact checks from  and only enforces SARIF/browser artifacts on full profiles (/ or fail-closed default).
-  now applies shared requirement registry gates (, , ) and treats missing/empty  as full requirements (fail-closed).
-  enrichment now carries  plus computed  while preserving / metadata.
-  release-readiness execution primitives now pin  and expose machine-readable  in check output.
- Added coverage across proof/claim/query/compiler tests for  light path,  full path, and missing/empty  fail-closed behavior.

## [2026-03-09] Task 5 COMPLETE - profile-aware proof/claim/query/release gates
- runtime/proof_gate.py now resolves required artifact checks from requirements_for_profile(evidence_profile) and only enforces SARIF/browser artifacts on full profiles (release/security-audit or fail-closed default).
- runtime/claim_judge.py now applies shared requirement registry gates (tests, trace_link, security_scan) and treats missing/empty evidence_profile as full requirements (fail-closed).
- runtime/evidence_query.py enrichment now carries evidence_profile plus computed evidence_requirements while preserving profile_version/intent_gate_version metadata.
- runtime/contract_compiler.py release-readiness execution primitives now pin evidence_profile=release and expose machine-readable required_evidence_requirements in check output.
- Added coverage across proof/claim/query/compiler tests for docs-only light path, release full path, and missing/empty evidence_profile fail-closed behavior.
