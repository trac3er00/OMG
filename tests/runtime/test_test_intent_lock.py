from __future__ import annotations

from runtime.test_intent_lock import evaluate_test_delta


def test_weaker_assertions_fail() -> None:
    result = evaluate_test_delta(
        {
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 2}],
            "override": {},
        }
    )

    assert result["verdict"] == "fail"
    assert "weakened_assertions" in result["flags"]


def test_integration_to_mock_without_override_fails() -> None:
    result = evaluate_test_delta(
        {
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "mock", "assertions": 4}],
            "override": {},
        }
    )

    assert result["verdict"] == "fail"
    assert "integration_to_mock_downgrade" in result["flags"]


def test_valid_delta_passes() -> None:
    result = evaluate_test_delta(
        {
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "override": {},
        }
    )

    assert result["verdict"] == "pass"
    assert result["reasons"] == []


def test_override_allows_waived_delta() -> None:
    result = evaluate_test_delta(
        {
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "mock", "assertions": 1}],
            "override": {"reason": "covered by upstream contract test"},
        }
    )

    assert result["verdict"] == "pass"
    assert "override_present" in result["flags"]
