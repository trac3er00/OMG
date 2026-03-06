"""Checks for standalone verification script safety."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_verify_standalone_excludes_legacy_omc_dir():
    script = (ROOT / "scripts" / "verify-standalone.sh").read_text(encoding="utf-8")
    assert '--exclude="./.omc"' in script


def test_source_build_drift_script_exists():
    assert (ROOT / "scripts" / "check-source-build-drift.py").exists()


def test_runtime_readiness_workflow_exists_with_expected_gates():
    workflow = ROOT / ".github" / "workflows" / "omg-runtime-readiness.yml"
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "scripts/check-source-build-drift.py" in text
    assert "tests/runtime tests/scripts/test_omg_cli.py tests/e2e/test_provider_live_smoke.py" in text
    assert "tests/e2e/test_provider_native_entrypoints.py" in text
    assert "tests/e2e/test_runtime_long_horizon.py" in text
    assert "tests/hooks tests/security tests/performance" in text
    assert "tests/performance/test_runtime_stress_budget.py" in text
    assert "python3 -m pytest -q" in text


def test_nightly_provider_smoke_workflow_exists_with_artifacts():
    workflow = ROOT / ".github" / "workflows" / "omg-nightly-provider-smoke.yml"
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "providers status --smoke" in text
    assert "providers smoke" in text
    assert "tests/e2e/test_runtime_long_horizon.py" in text
    assert "tests/performance/test_runtime_stress_budget.py" in text
    assert "upload-artifact" in text


def test_readme_documents_readiness_reason_model():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "local_steps" in text
    assert "provider_steps" in text
    assert "native_ready_reasons" in text
    assert "dispatch_ready_reasons" in text
    assert "providers repair" in text
    assert "release readiness" in text
