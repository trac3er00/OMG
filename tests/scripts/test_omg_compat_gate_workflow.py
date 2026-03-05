"""Regression tests for the OMG compat GitHub workflow."""
from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "omg-compat-gate.yml"
PYPROJECT = ROOT / "pyproject.toml"


def test_compat_gate_installs_project_test_dependencies() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'pip install ".[test]"' in text
    assert text.count('pip install ".[test]"') == 2


def test_project_declares_pyyaml_for_setup_wizard() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert any(dep.lower().startswith("pyyaml") for dep in dependencies)
