from __future__ import annotations

import importlib

from runtime.delta_classifier import classify_project_changes


def test_classifier_keeps_auth_category_behavior(tmp_path):
    result = classify_project_changes(
        str(tmp_path),
        touched_files=["src/auth/login.py"],
        goal="stabilize auth token refresh",
    )

    assert "auth" in result["categories"]


def test_classifier_keeps_payment_and_api_category_behavior(tmp_path):
    result = classify_project_changes(
        str(tmp_path),
        touched_files=["services/checkout/endpoint.py"],
        goal="update payment endpoint contract",
    )

    assert "payment" in result["categories"]
    assert "api" in result["categories"]


def test_classifier_keeps_implementation_default_category(tmp_path):
    result = classify_project_changes(
        str(tmp_path),
        touched_files=["src/feature/widget.py"],
        goal="small refactor",
    )

    assert result["categories"] == ["implementation"]


def test_classifier_adds_additive_evidence_profile(tmp_path):
    result = classify_project_changes(
        str(tmp_path),
        touched_files=["docs/guide.md"],
        goal="update docs",
    )

    assert "categories" in result
    assert "evidence_profile" in result
    assert result["evidence_profile"] == "docs-only"


def test_requirements_fail_closed_for_missing_profile():
    registry = importlib.import_module("runtime.evidence_requirements")
    assert registry.requirements_for_profile(None) == registry.FULL_REQUIREMENTS


def test_requirements_fail_closed_for_empty_profile():
    registry = importlib.import_module("runtime.evidence_requirements")
    assert registry.requirements_for_profile("") == registry.FULL_REQUIREMENTS
