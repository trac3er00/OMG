- Updated README.md, settings.json, and docs/proof.md to use canonical modes (chill, focused, exploratory).
- Set "omgMode": "focused" as the default in settings.json.
- Updated integration tests to verify the default mode selection in the setup wizard.
- Verified all tests pass and public readiness check is successful.


## [2026-03-08] Task 14 - Gemini/Kimi compiler outputs and host parity
- Added `_compile_gemini_outputs()` and `_compile_kimi_outputs()` in `runtime/contract_compiler.py`; both write stdio `omg-control` MCP configs via `runtime.mcp_config_writers` to `.gemini/settings.json` and `.kimi/mcp.json` respectively.
- Dist manifests now record a `hosts` array from compile selection; release-readiness uses this to enforce host artifact parity per manifest channel instead of globally forcing all providers.
- Provider readiness and provider-host parity checks are now scoped to hosts declared by compiled manifests, preventing false blockers when local binaries for non-requested hosts are installed.
- `scripts/omg.py contract compile --host ...` argparse choices now include `gemini` and `kimi`; without this, CLI verification commands fail before contract compiler execution.


## [2026-03-08] Task 15 - Packaging migration & bundle_promotion_parity fix
- The `bundle_promotion_parity` blocker required 3 conditions: (1) settings.json `required_bundles` includes all 4 TRUTH_COUNCIL_BUNDLES, (2) `dist/{public,enterprise}/bundle/.agents/skills/omg/{bundle_id}/SKILL.md` exists for each, (3) `pyproject.toml` has `".agents/skills/omg/{bundle_id}" = ` data-files entries. Conditions 1 and 3 were already met; only condition 2 (dist files) was missing.
- The dist bundle SKILL.md files were previously tracked in git but deleted from the working tree. Public versions matched HEAD after restore; enterprise versions had minor content diffs requiring a commit.
- The `_check_bundle_promotion_parity()` function in `contract_compiler.py` (line 2005) uses `output_root` which defaults to project root via `_resolve_output_root()`.
- `pyproject.toml` `data-files` and `package-data` sections can coexist — data-files provides install-time file placement, package-data provides in-package inclusion. Both are needed for the dual verification paths.
- Full pytest with coverage and `-k "packag or standalone or asset_loader or contract_compiler"` selects 79 tests and times out (>2 min). The package_smoke check builds a wheel which is slow. Running specific test files without coverage is fast.


## [2026-03-08] Task 16 - Labs-only forge orchestration surface
- Forge reuses `lab.pipeline.run_pipeline()` directly — no second orchestration path. The preset gate is at the CLI handler level (`cmd_forge_run` checks `--preset != "labs"` before calling pipeline).
- VALID_PRESETS is imported from `runtime.adoption` and used as argparse choices for `--preset`, so invalid presets are caught by argparse before reaching the handler.
- The `add_subparsers` pattern with `dest` + `required=True` is the standard CLI extension pattern in `omg.py` — forge follows the same shape as lab/security/contract subcommands.
- Tests use both direct `run_pipeline()` calls for policy-level assertions and `subprocess.run()` for CLI-level assertions (help output, preset gating). Subprocess tests use temp files for job JSON to avoid inline JSON quoting issues.


## [2026-03-08] Task 17 - End-to-end four-host release verification
- Ran full CLI acceptance wave successfully: `contract validate`, public+enterprise `contract compile` with hosts `claude/codex/gemini/kimi`, `release readiness --channel dual`, and `check-omg-public-ready.py` all returned status `ok` (readiness blockers `[]`).
- Targeted pytest verification passed across roadmap areas: proof chain (18), contract compiler/public surface (50), security enrichment (41), background/HUD (23), session snapshot+rollback (131), mode profiles (159), forge/labs/domain packs/policies (51).
- Failure-path check confirmed release gate behavior: removing `dist/public/bundle/.agents/skills/omg/plan-council/SKILL.md` flips readiness to `error` with `bundle_promotion_parity`; restoring the file returns readiness to `ok` with no blockers.
- Captured machine evidence in `.sisyphus/evidence/task-17-full-roadmap-verification.txt` and `.sisyphus/evidence/task-17-full-roadmap-verification-error.txt`.
