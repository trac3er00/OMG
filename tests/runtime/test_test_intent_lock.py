from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from runtime.test_intent_lock import evaluate_test_delta, lock_intent, verify_intent, verify_lock


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


def test_lock_intent_captures_proactive_contract_hashes(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_auth.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_login():\n    assert True\n", encoding="utf-8")

    lock = lock_intent(
        tmp_path.as_posix(),
        {
            "goal": "fix auth",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
            "assertions": [{"name": "integration-auth", "assertions": 4}],
            "skip_markers": ["pytest.mark.skip"],
            "waiver": {"id": "waiver-1"},
        },
    )

    payload = json.loads(Path(lock["path"]).read_text(encoding="utf-8"))
    assert payload["test_selectors"] == ["tests/test_auth.py::test_login"]
    assert payload["test_file_hashes"]["tests/test_auth.py"] == sha256(test_file.read_bytes()).hexdigest()
    assert payload["covered_paths"] == ["app/auth.py"]
    assert payload["assertion_metadata"] == [{"name": "integration-auth", "assertions": 4}]
    assert payload["skip_markers"] == ["pytest.mark.skip"]
    assert payload["waiver"] == {"id": "waiver-1"}


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


def test_evaluate_test_delta_uses_lock_contract_when_lock_id_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    test_file = tmp_path / "tests" / "test_auth.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_login():\n    assert True\n", encoding="utf-8")

    lock = lock_intent(
        ".",
        {
            "goal": "fix auth",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
        },
    )
    result = evaluate_test_delta(
        {
            "lock_id": lock["lock_id"],
            "tests": ["tests/test_auth.py::test_logout"],
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "override": {},
        }
    )

    assert result["verdict"] == "fail"
    assert "locked_selectors_mismatch" in result["flags"]


def test_weakened_assertions_with_lock_id_still_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    test_file = tmp_path / "tests" / "test_auth.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_login():\n    assert True\n", encoding="utf-8")

    lock = lock_intent(
        ".",
        {
            "goal": "fix auth",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
            "assertions": [{"name": "integration-auth", "assertions": 4}],
        },
    )
    result = evaluate_test_delta(
        {
            "lock_id": lock["lock_id"],
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 1}],
            "override": {},
        }
    )

    assert result["verdict"] == "fail"
    assert "weakened_assertions" in result["flags"]


def test_waiver_artifact_allows_lock_contract_bypass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    test_file = tmp_path / "tests" / "test_auth.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_login():\n    assert True\n", encoding="utf-8")

    lock = lock_intent(
        ".",
        {
            "goal": "fix auth",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
        },
    )
    result = evaluate_test_delta(
        {
            "lock_id": lock["lock_id"],
            "tests": ["tests/test_auth.py::test_logout"],
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "mock", "assertions": 1}],
            "override": {},
            "waiver_artifact": {"id": "waiver-42", "approved_by": "user"},
        }
    )

    assert result["verdict"] == "pass"
    assert "waiver_artifact_present" in result["flags"]


def test_verify_lock_returns_missing_lock_when_run_has_no_lock(tmp_path: Path) -> None:
    verdict = verify_lock(tmp_path.as_posix(), run_id="run-123")

    assert verdict["status"] == "missing_lock"
    assert verdict["reason"] == "no_active_test_intent_lock"


def test_verify_lock_reports_contract_mismatch_for_explicit_lock(tmp_path: Path) -> None:
    lock = lock_intent(
        tmp_path.as_posix(),
        {
            "goal": "fix auth",
            "run_id": "run-a",
            "tests": ["tests/test_auth.py::test_login"],
        },
    )

    verdict = verify_lock(tmp_path.as_posix(), run_id="run-b", lock_id=lock["lock_id"])
    assert verdict["status"] == "lock_contract_mismatch"
    assert verdict["reason"] == "run_id_mismatch"


def test_verify_lock_returns_ok_for_matching_run_and_lock(tmp_path: Path) -> None:
    lock = lock_intent(
        tmp_path.as_posix(),
        {
            "goal": "fix auth",
            "run_id": "run-ok",
            "tests": ["tests/test_auth.py::test_login"],
        },
    )

    verdict = verify_lock(tmp_path.as_posix(), run_id="run-ok", lock_id=lock["lock_id"])
    assert verdict["status"] == "ok"
    assert verdict["lock_id"] == lock["lock_id"]
