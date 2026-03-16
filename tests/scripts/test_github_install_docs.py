# pyright: reportMissingImports=false
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_INSTALL = ROOT / "docs" / "install"


def test_github_action_doc_exists() -> None:
    path = DOCS_INSTALL / "github-action.md"
    assert path.exists(), "docs/install/github-action.md must exist"


def test_github_action_doc_contains_stable_check_name() -> None:
    text = (DOCS_INSTALL / "github-action.md").read_text(encoding="utf-8")
    assert "OMG PR Reviewer" in text, (
        "docs/install/github-action.md must document the stable check name 'OMG PR Reviewer'"
    )


def test_github_action_doc_references_action_yml() -> None:
    text = (DOCS_INSTALL / "github-action.md").read_text(encoding="utf-8")
    assert "action.yml" in text, (
        "docs/install/github-action.md must reference action.yml as the consumable entrypoint"
    )


def test_github_app_doc_contains_stable_check_name_section() -> None:
    text = (DOCS_INSTALL / "github-app.md").read_text(encoding="utf-8")
    assert "Stable Check Name" in text, (
        "docs/install/github-app.md must contain a 'Stable Check Name' section"
    )
