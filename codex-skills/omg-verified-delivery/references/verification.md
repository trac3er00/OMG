# OMG Verification Reference

Preferred verification sweep for provider/runtime realignment work:

- `python3 -m pytest -q tests/runtime tests/scripts/test_omg_cli.py tests/e2e/test_provider_live_smoke.py tests/e2e/test_provider_native_entrypoints.py tests/e2e/test_runtime_long_horizon.py tests/e2e/test_setup_script.py tests/scripts/test_source_build_drift.py tests/test_claude_plugin_manifest.py tests/e2e/test_omg_hud.py`
- `python3 scripts/check-source-build-drift.py`
- `rg -n "legacy provider strings" .` after replacing the pattern with the exact strings you are retiring

If any step is skipped, say so explicitly in the final report.
