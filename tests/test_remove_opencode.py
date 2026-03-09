"""Regression tests confirming OpenCode is a supported compatibility host."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_opencode_provider_module_exists():
    assert (ROOT / "runtime" / "providers" / "opencode_provider.py").exists()

def test_opencode_install_doc_exists():
    assert (ROOT / "docs" / "install" / "opencode.md").exists()

def test_readme_references_opencode():
    content = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "opencode" in content

def test_opencode_provider_is_importable():
    from runtime.providers.opencode_provider import OpenCodeProvider
    p = OpenCodeProvider()
    assert p.get_name() == "opencode"
