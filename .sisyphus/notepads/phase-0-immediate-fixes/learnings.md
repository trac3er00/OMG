
## Task 3: Plugin Command Path Audit in Readiness Gate

- Core plugin command paths resolve relative to ROOT (e.g., `root / "commands/OMG:setup.md"`)
- Advanced plugin command paths resolve relative to `root / "plugins" / "advanced"` (plugin-relative)
- Sub-check return shape: `{"status": "ok"|"error", "blockers": [...], "details": {...}}`
- Wiring pattern: assign to `checks[key]`, then `blockers.extend(check.get("blockers", []))`
- `_patch_fast_release_checks` only stubs expensive checks (pip wheel, mcp fabric, version drift); cheap file-existence checks don't need stubbing
- Only one test uses `root_dir=tmp_path` (version drift test) and it already expects `status == "error"`, so adding new blockers from missing manifests doesn't break it
- Test scaffold helper (`_scaffold_plugin_tree`) with keyword arg for missing files keeps tests DRY
- Compiled advanced-plugin artifact requirements must be generated from `plugins/advanced/plugin.json` to avoid stale command expectations in readiness checks.
- Required compiled artifacts are explicit (`bundle/plugins/advanced/plugin.json` + each manifest command `path`), not directory-glob based.
- Release-readiness coverage is strongest when it asserts both sides: deprecated command artifacts are not required and manifest-declared command artifacts still block when missing.

## Task 5: Version Purge (2.1.1)

- 12 files touched across scripts, docs, CI workflows, and tests
- Test file `test_validate_release_identity.py` needed `_OLD_VERSION = "0.0.1-test"` constant — every `"2.1.1"` replaced, including those embedded in JSON/JS fixture strings (required f-strings or `json.dumps()`)
- Shell script `verify-standalone.sh` now uses `FORBID_VERSION` env var instead of hardcoded version
- CI workflows use `"${FORBID_VERSION:-}"` — empty default makes the check a no-op when unset, which is acceptable
- CHANGELOG historical entry rewritten from `## 2.1.1` to `## [historical] 2.1.x` to preserve context while removing literal
- Assertions tightened: `returncode in (0, 1)` → `returncode == 0`, `overall_status in ("ok", "fail")` → `overall_status == "ok"`
- All 15 tests pass, grep shows zero matches, validator exits 0
