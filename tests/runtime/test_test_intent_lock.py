from __future__ import annotations

import json
from pathlib import Path

from runtime.test_intent_lock import evaluate_test_delta, lock_intent, verify_intent


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


def test_lock_intent_persists_state(tmp_path: Path) -> None:
    lock = lock_intent(tmp_path.as_posix(), {"goal": "fix auth", "tests": ["tests/test_auth.py::test_login"]})

    assert lock["status"] == "locked"
    lock_path = Path(lock["path"])
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["lock_id"] == lock["lock_id"]
    assert payload["intent"]["tests"] == ["tests/test_auth.py::test_login"]


def test_verify_intent_returns_ok_on_matching_tests(tmp_path: Path) -> None:
    lock = lock_intent(tmp_path.as_posix(), {"goal": "fix auth", "tests": ["tests/test_auth.py::test_login"]})

    verdict = verify_intent(
        tmp_path.as_posix(),
        lock["lock_id"],
        {"tests": ["tests/test_auth.py::test_login"], "weakened_assertions": []},
    )

    assert verdict == {"status": "ok", "lock_id": lock["lock_id"], "reasons": []}


def test_verify_intent_fails_on_weakened_assertions(tmp_path: Path) -> None:
    lock = lock_intent(tmp_path.as_posix(), {"goal": "fix auth", "tests": ["tests/test_auth.py::test_login"]})

    verdict = verify_intent(
        tmp_path.as_posix(),
        lock["lock_id"],
        {
            "tests": ["tests/test_auth.py::test_login"],
            "weakened_assertions": ["tests/test_auth.py::test_login"],
        },
    )

    assert verdict["status"] == "fail"
    assert "weakened_assertions_present" in verdict["reasons"]


def test_verify_intent_fails_on_test_mismatch(tmp_path: Path) -> None:
    lock = lock_intent(tmp_path.as_posix(), {"goal": "fix auth", "tests": ["tests/test_auth.py::test_login"]})

    verdict = verify_intent(
        tmp_path.as_posix(),
        lock["lock_id"],
        {"tests": ["tests/test_auth.py::test_logout"], "weakened_assertions": []},
    )

    assert verdict["status"] == "fail"
    assert "tests_mismatch" in verdict["reasons"]


def test_verify_intent_returns_missing_lock_when_not_found(tmp_path: Path) -> None:
    verdict = verify_intent(tmp_path.as_posix(), "missing-lock", {"tests": [], "weakened_assertions": []})

    assert verdict["status"] == "missing_lock"
    assert verdict["lock_id"] == "missing-lock"
