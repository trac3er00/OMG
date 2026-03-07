"""Regression tests for complete OpenCode removal."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_docs_do_not_reference_opencode():
    for rel in [
        "README.md",
        "docs/proof.md",
        "plugins/README.md",
        "commands/OMG:setup.md",
        "docs/release-checklist.md",
    ]:
        content = (ROOT / rel).read_text(encoding="utf-8").lower()
        assert "opencode" not in content
        assert "opencode-ai" not in content


def test_opencode_install_doc_is_removed():
    assert not (ROOT / "docs" / "install" / "opencode.md").exists()


def test_opencode_provider_module_is_removed():
    assert not (ROOT / "runtime" / "providers" / "opencode_provider.py").exists()
