from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from runtime.test_intent_lock import evaluate_test_delta, lock_intent, verify_done_when, verify_intent, verify_lock

_FIXTURE_TEST_CONTENT = (
    "from app.auth import authenticate\n"
    "\n"
    "\n"
    "def test_login():\n"
    "    result = authenticate('user', 'pass123')\n"
    "    assert result.status_code == 200\n"
    "    assert result.json()['token'] is not None\n"
)


@pytest.fixture()
def auth_project(tmp_path: Path) -> Path:
    """Scaffold a minimal project with a test file for intent-lock testing."""
    test_file = tmp_path / "tests" / "test_auth.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(_FIXTURE_TEST_CONTENT, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# evaluate_test_delta — user modifies code, system guards test quality
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "old_kind, old_count, new_kind, new_count, override, expected_verdict, expected_flags",
    [
        pytest.param(
            "integration", 4, "integration", 2, {},
            "fail", ["weakened_assertions"],
            id="fewer-assertions-blocks",
        ),
        pytest.param(
            "integration", 4, "mock", 4, {},
            "fail", ["integration_to_mock_downgrade"],
            id="mock-downgrade-without-override-blocks",
        ),
        pytest.param(
            "integration", 4, "integration", 4, {},
            "pass", [],
            id="unchanged-delta-passes",
        ),
        pytest.param(
            "integration", 4, "mock", 1,
            {"reason": "covered by upstream contract test"},
            "pass", ["override_present"],
            id="explicit-override-allows-downgrade",
        ),
        pytest.param(
            "integration", 4, "snapshot", 4, {},
            "fail", ["snapshot_only_refresh"],
            id="snapshot-only-replacement-blocks",
        ),
    ],
)
def test_evaluate_test_delta_verdicts(
    old_kind: str,
    old_count: int,
    new_kind: str,
    new_count: int,
    override: dict[str, object],
    expected_verdict: str,
    expected_flags: list[str],
) -> None:
    result = evaluate_test_delta(
        {
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": old_kind, "assertions": old_count}],
            "new_tests": [{"name": "integration-auth", "kind": new_kind, "assertions": new_count}],
            "override": override,
        }
    )

    assert result["verdict"] == expected_verdict
    for flag in expected_flags:
        assert flag in result["flags"]
    if not expected_flags and expected_verdict == "pass":
        assert result["reasons"] == []


def test_removing_all_tests_for_touched_paths_blocks() -> None:
    """User removes every test covering modified code — system catches the gap."""
    result = evaluate_test_delta(
        {
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [],
            "override": {},
        }
    )

    assert result["verdict"] == "fail"
    assert "removed_touched_area_coverage" in result["flags"]


# ---------------------------------------------------------------------------
# lock_intent — user declares what they intend to test before starting work
# ---------------------------------------------------------------------------

def test_lock_intent_persists_state(tmp_path: Path) -> None:
    lock = lock_intent(tmp_path.as_posix(), {"goal": "fix auth", "tests": ["tests/test_auth.py::test_login"]})

    assert lock["status"] == "locked"
    lock_path = Path(lock["path"])
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["lock_id"] == lock["lock_id"]
    assert payload["intent"]["tests"] == ["tests/test_auth.py::test_login"]


def test_lock_intent_captures_proactive_contract_hashes(auth_project: Path) -> None:
    test_file = auth_project / "tests" / "test_auth.py"

    lock = lock_intent(
        auth_project.as_posix(),
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


# ---------------------------------------------------------------------------
# verify_intent — after work, system checks results against locked intent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "result_tests, weakened, expected_status, expected_reason",
    [
        pytest.param(
            ["tests/test_auth.py::test_login"], [], "ok", None,
            id="matching-tests-pass",
        ),
        pytest.param(
            ["tests/test_auth.py::test_login"],
            ["tests/test_auth.py::test_login"],
            "fail", "weakened_assertions_present",
            id="weakened-assertions-block",
        ),
        pytest.param(
            ["tests/test_auth.py::test_logout"], [], "fail", "tests_mismatch",
            id="different-tests-block",
        ),
    ],
)
def test_verify_intent_outcomes(
    tmp_path: Path,
    result_tests: list[str],
    weakened: list[str],
    expected_status: str,
    expected_reason: str | None,
) -> None:
    lock = lock_intent(tmp_path.as_posix(), {"goal": "fix auth", "tests": ["tests/test_auth.py::test_login"]})

    verdict = verify_intent(
        tmp_path.as_posix(),
        lock["lock_id"],
        {"tests": result_tests, "weakened_assertions": weakened},
    )

    assert verdict["status"] == expected_status
    if expected_reason:
        assert expected_reason in verdict["reasons"]
    else:
        assert verdict["reasons"] == []


def test_verify_intent_returns_missing_lock_when_not_found(tmp_path: Path) -> None:
    verdict = verify_intent(tmp_path.as_posix(), "missing-lock", {"tests": [], "weakened_assertions": []})

    assert verdict["status"] == "missing_lock"
    assert verdict["lock_id"] == "missing-lock"


# ---------------------------------------------------------------------------
# lock-aware evaluate_test_delta — delta checked against locked contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "lock_extras, delta_tests, new_kind, new_count, delta_extras, expected_verdict, expected_flag",
    [
        pytest.param(
            {}, ["tests/test_auth.py::test_logout"], "integration", 4, {},
            "fail", "locked_selectors_mismatch",
            id="different-selectors-from-lock-blocks",
        ),
        pytest.param(
            {"assertions": [{"name": "integration-auth", "assertions": 4}]},
            ["tests/test_auth.py::test_login"], "integration", 1, {},
            "fail", "weakened_assertions",
            id="weakened-assertions-with-lock-still-blocks",
        ),
        pytest.param(
            {}, ["tests/test_auth.py::test_logout"], "mock", 1,
            {"waiver_artifact": {"id": "waiver-42", "approved_by": "user"}},
            "pass", "waiver_artifact_present",
            id="waiver-artifact-bypasses-lock-violations",
        ),
    ],
)
def test_locked_contract_enforcement(
    auth_project: Path,
    monkeypatch,
    lock_extras: dict[str, object],
    delta_tests: list[str],
    new_kind: str,
    new_count: int,
    delta_extras: dict[str, object],
    expected_verdict: str,
    expected_flag: str,
) -> None:
    monkeypatch.chdir(auth_project)

    lock = lock_intent(
        ".",
        {
            "goal": "fix auth",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
            **lock_extras,
        },
    )
    result = evaluate_test_delta(
        {
            "lock_id": lock["lock_id"],
            "tests": delta_tests,
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": new_kind, "assertions": new_count}],
            "override": {},
            **delta_extras,
        }
    )

    assert result["verdict"] == expected_verdict
    assert expected_flag in result["flags"]


@pytest.mark.parametrize(
    "tamper_action, expected_flag",
    [
        pytest.param("delete", "locked_test_file_missing", id="test-file-deleted-after-lock"),
        pytest.param("modify", "locked_test_file_changed", id="test-file-modified-after-lock"),
    ],
)
def test_test_file_tampering_after_lock_blocks(
    auth_project: Path,
    monkeypatch,
    tamper_action: str,
    expected_flag: str,
) -> None:
    """User deletes or modifies a locked test file — system detects the breach."""
    monkeypatch.chdir(auth_project)
    lock = lock_intent(
        ".",
        {
            "goal": "fix auth",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
        },
    )

    test_file = auth_project / "tests" / "test_auth.py"
    if tamper_action == "delete":
        test_file.unlink()
    else:
        test_file.write_text("def test_login():\n    pass  # gutted\n", encoding="utf-8")

    result = evaluate_test_delta(
        {
            "lock_id": lock["lock_id"],
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "override": {},
        }
    )

    assert result["verdict"] == "fail"
    assert expected_flag in result["flags"]


def test_stale_lock_id_reference_blocks(tmp_path: Path) -> None:
    """User references a lock_id that doesn't exist on disk — system fails closed."""
    result = evaluate_test_delta(
        {
            "lock_id": "nonexistent-lock-id",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "override": {},
        },
        project_dir=tmp_path.as_posix(),
    )

    assert result["verdict"] == "fail"
    assert "missing_lock_state" in result["flags"]


# ---------------------------------------------------------------------------
# verify_lock — system validates lock state against active run
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "lock_run_id, verify_run_id, expected_status, expected_reason",
    [
        pytest.param(
            None, "run-123", "missing_lock", "no_active_test_intent_lock",
            id="no-lock-reports-missing",
        ),
        pytest.param(
            "run-a", "run-b", "lock_contract_mismatch", "run_id_mismatch",
            id="cross-run-mismatch-blocks",
        ),
        pytest.param(
            "run-ok", "run-ok", "ok", "active_test_intent_lock",
            id="matching-run-passes",
        ),
    ],
)
def test_verify_lock_outcomes(
    tmp_path: Path,
    lock_run_id: str | None,
    verify_run_id: str,
    expected_status: str,
    expected_reason: str,
) -> None:
    lock_id = None
    if lock_run_id is not None:
        lock = lock_intent(
            tmp_path.as_posix(),
            {"goal": "fix auth", "run_id": lock_run_id, "tests": ["tests/test_auth.py::test_login"]},
        )
        lock_id = lock["lock_id"]

    verdict = verify_lock(tmp_path.as_posix(), run_id=verify_run_id, lock_id=lock_id)
    assert verdict["status"] == expected_status
    assert verdict["reason"] == expected_reason


def test_verify_lock_discovers_lock_by_run_id(tmp_path: Path) -> None:
    """User calls verify_lock with just run_id — system auto-discovers the matching lock."""
    lock = lock_intent(
        tmp_path.as_posix(),
        {"goal": "fix auth", "run_id": "run-auto", "tests": ["tests/test_auth.py::test_login"]},
    )

    verdict = verify_lock(tmp_path.as_posix(), run_id="run-auto")

    assert verdict["status"] == "ok"
    assert verdict["run_id"] == "run-auto"
    assert verdict["lock_id"] == lock["lock_id"]


def test_verify_lock_with_no_identifiers_reports_missing(tmp_path: Path) -> None:
    """User calls verify_lock with neither run_id nor lock_id — system reports missing."""
    verdict = verify_lock(tmp_path.as_posix(), run_id=None)

    assert verdict["status"] == "missing_lock"
    assert verdict["run_id"] is None


# ---------------------------------------------------------------------------
# verify_done_when — system enforces done_when metadata before completion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "metadata, run_id, expected_status, expected_reason, expected_criteria",
    [
        pytest.param(
            None, "run-1", "ok", "done_when_not_provided", None,
            id="none-metadata-allows",
        ),
        pytest.param(
            {}, "run-1", "ok", "done_when_not_declared", None,
            id="empty-dict-blocks",
        ),
        pytest.param(
            {"done_when": ""}, "run-1", "missing_done_when", "done_when_required", None,
            id="empty-string-blocks",
        ),
        pytest.param(
            {"done_when": "all tests pass"}, None,
            "ok", "done_when_present", ["all tests pass"],
            id="string-criteria-passes",
        ),
        pytest.param(
            {"done_when": ["lint clean", "tests pass"]}, "run-2",
            "ok", "done_when_present", ["lint clean", "tests pass"],
            id="list-criteria-passes",
        ),
        pytest.param(
            {"done_when": {"criteria": ["build ok", "no regressions"]}}, "run-3",
            "ok", "done_when_present", ["build ok", "no regressions"],
            id="dict-criteria-list-passes",
        ),
        pytest.param(
            {"done_when": {"summary": "deploy complete"}}, "run-4",
            "ok", "done_when_present", ["deploy complete"],
            id="dict-summary-fallback-passes",
        ),
        pytest.param(
            {"done_when": {"criteria": "single criterion", "run_id": "run-A"}}, "run-B",
            "done_when_contract_mismatch", "done_when_run_id_mismatch", None,
            id="run-id-mismatch-blocks",
        ),
        pytest.param(
            {"done_when": {"criteria": "check passes", "run_id": "run-X"}}, "run-X",
            "ok", "done_when_present", ["check passes"],
            id="matching-run-id-passes",
        ),
    ],
)
def test_verify_done_when_outcomes(
    metadata: dict[str, object] | None,
    run_id: str | None,
    expected_status: str,
    expected_reason: str,
    expected_criteria: list[str] | None,
) -> None:
    """User declares completion criteria — system validates before accepting."""
    result = verify_done_when(metadata, run_id)

    assert result["status"] == expected_status
    assert result["reason"] == expected_reason
    if expected_criteria is not None:
        assert result["done_when"] == expected_criteria
    else:
        assert "done_when" not in result


# ---------------------------------------------------------------------------
# off-cwd regression — project_dir resolution must not depend on cwd
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "delta_tests, expected_verdict, expected_flag",
    [
        pytest.param(
            ["tests/test_auth.py::test_login"], "pass", None,
            id="matching-selectors-pass",
        ),
        pytest.param(
            ["tests/test_auth.py::test_logout"], "fail", "locked_selectors_mismatch",
            id="mismatched-selectors-caught",
        ),
    ],
)
def test_off_cwd_project_dir_resolution(
    auth_project: Path,
    delta_tests: list[str],
    expected_verdict: str,
    expected_flag: str | None,
) -> None:
    """Regression: evaluate_test_delta must resolve paths via project_dir, not cwd."""
    lock = lock_intent(
        auth_project.as_posix(),
        {
            "goal": "fix auth",
            "tests": ["tests/test_auth.py::test_login"],
            "touched_paths": ["app/auth.py"],
        },
    )

    result = evaluate_test_delta(
        {
            "lock_id": lock["lock_id"],
            "tests": delta_tests,
            "touched_paths": ["app/auth.py"],
            "old_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "new_tests": [{"name": "integration-auth", "kind": "integration", "assertions": 4}],
            "override": {},
        },
        project_dir=auth_project.as_posix(),
    )

    assert result["verdict"] == expected_verdict
    if expected_flag:
        assert expected_flag in result["flags"]
