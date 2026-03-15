from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4


def lock_intent(project_dir: str, intent: dict[str, Any]) -> dict[str, Any]:
    lock_id = str(uuid4())
    lock_dir = Path(project_dir) / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)

    lock_path = lock_dir / f"{lock_id}.json"
    test_selectors = _normalize_string_list(intent.get("tests") if isinstance(intent, dict) else None)
    covered_paths = _normalize_paths(intent.get("touched_paths") if isinstance(intent, dict) else None)
    assertion_metadata = _normalize_assertion_metadata(intent.get("assertions") if isinstance(intent, dict) else None)
    skip_markers = _normalize_string_list(intent.get("skip_markers") if isinstance(intent, dict) else None)
    waiver = intent.get("waiver") if isinstance(intent, dict) and isinstance(intent.get("waiver"), dict) else {}

    test_file_hashes: dict[str, str | None] = {}
    for selector in test_selectors:
        selector_path = _selector_to_path(selector)
        if selector_path in test_file_hashes:
            continue
        hash_value = _hash_test_file(Path(project_dir), selector_path)
        test_file_hashes[selector_path] = hash_value

    payload = {
        "schema": "TestIntentLock",
        "lock_id": lock_id,
        "intent": intent,
        "test_selectors": test_selectors,
        "test_file_hashes": test_file_hashes,
        "assertion_metadata": assertion_metadata,
        "skip_markers": skip_markers,
        "covered_paths": covered_paths,
        "waiver": waiver,
    }
    lock_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return {"lock_id": lock_id, "status": "locked", "path": str(lock_path)}


def verify_intent(project_dir: str, lock_id: str, results: dict[str, Any]) -> dict[str, Any]:
    lock_path = Path(project_dir) / ".omg" / "state" / "test-intent-lock" / f"{lock_id}.json"
    if not lock_path.exists():
        return {"status": "missing_lock", "lock_id": lock_id, "reasons": ["missing lock state"]}

    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "missing_lock", "lock_id": lock_id, "reasons": ["missing lock state"]}

    intent = payload.get("intent") if isinstance(payload, dict) else {}
    intent_tests = _normalize_string_list(intent.get("tests") if isinstance(intent, dict) else None)
    result_tests = _normalize_string_list(results.get("tests"))
    weakened_assertions = results.get("weakened_assertions")

    reasons: list[str] = []
    if isinstance(weakened_assertions, list) and weakened_assertions:
        reasons.append("weakened_assertions_present")

    if result_tests != intent_tests:
        reasons.append("tests_mismatch")

    status = "ok" if not reasons else "fail"
    return {"status": status, "lock_id": lock_id, "reasons": reasons}


def verify_lock(project_dir: str, run_id: str | None, lock_id: str | None = None) -> dict[str, Any]:
    normalized_run_id = str(run_id or "").strip()
    normalized_lock_id = str(lock_id or "").strip()

    if normalized_lock_id:
        payload = _load_lock_payload_from_project(project_dir, normalized_lock_id)
        if payload is None:
            return {
                "status": "missing_lock",
                "reason": "no_active_test_intent_lock",
                "run_id": normalized_run_id or None,
                "lock_id": normalized_lock_id,
            }

        contract_check = _check_run_contract(payload, normalized_run_id)
        if contract_check is not None:
            return {
                "status": "lock_contract_mismatch",
                "reason": contract_check,
                "run_id": normalized_run_id or None,
                "lock_id": normalized_lock_id,
            }

        return {
            "status": "ok",
            "reason": "active_test_intent_lock",
            "run_id": normalized_run_id or None,
            "lock_id": normalized_lock_id,
        }

    if not normalized_run_id:
        return {
            "status": "missing_lock",
            "reason": "no_active_test_intent_lock",
            "run_id": None,
            "lock_id": None,
        }

    lock_dir = Path(project_dir) / ".omg" / "state" / "test-intent-lock"
    if not lock_dir.exists():
        return {
            "status": "missing_lock",
            "reason": "no_active_test_intent_lock",
            "run_id": normalized_run_id,
            "lock_id": None,
        }

    for path in sorted(lock_dir.glob("*.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        payload = _load_lock_payload_from_path(path)
        if payload is None:
            continue
        intent = payload.get("intent")
        intent_run_id = ""
        if isinstance(intent, dict):
            intent_run_id = str(intent.get("run_id", "")).strip()
        if intent_run_id != normalized_run_id:
            continue
        lock_id_candidate = str(payload.get("lock_id", "")).strip() or path.stem
        return {
            "status": "ok",
            "reason": "active_test_intent_lock",
            "run_id": normalized_run_id,
            "lock_id": lock_id_candidate,
        }

    return {
        "status": "missing_lock",
        "reason": "no_active_test_intent_lock",
        "run_id": normalized_run_id,
        "lock_id": None,
    }


def verify_done_when(metadata: dict[str, Any] | None, run_id: str | None) -> dict[str, Any]:
    metadata_obj = metadata if isinstance(metadata, dict) else {}
    normalized_run_id = str(run_id or "").strip() or None

    if metadata is None:
        # No metadata provided at all -- treat the same as metadata without
        # a done_when key.  This is the common case for CLI / non-Claude
        # invocations and should not block.
        return {
            "status": "ok",
            "reason": "done_when_not_provided",
            "run_id": normalized_run_id,
            "done_when_declared": False,
            "done_when_completed": False,
        }

    if "done_when" not in metadata_obj:
        return {
            "status": "ok",
            "reason": "done_when_not_declared",
            "run_id": normalized_run_id,
            "done_when_declared": False,
            "done_when_completed": False,
        }

    criteria = _extract_done_when_criteria(metadata_obj.get("done_when"))
    if not criteria:
        return {
            "status": "missing_done_when",
            "reason": "done_when_required",
            "run_id": normalized_run_id,
            "done_when_declared": False,
            "done_when_completed": False,
        }

    done_when_run_id = _extract_done_when_run_id(metadata_obj.get("done_when"))
    if done_when_run_id and normalized_run_id and done_when_run_id != normalized_run_id:
        return {
            "status": "done_when_contract_mismatch",
            "reason": "done_when_run_id_mismatch",
            "run_id": normalized_run_id,
            "done_when_declared": True,
            "done_when_completed": False,
        }

    completion_state = _extract_done_when_completion_state(metadata_obj)
    done_when_completed = completion_state == "completed"

    return {
        "status": "ok",
        "reason": "done_when_present",
        "run_id": normalized_run_id or done_when_run_id or None,
        "done_when": criteria,
        "done_when_declared": True,
        "done_when_completed": done_when_completed,
        "done_when_state": completion_state,
    }


def evaluate_test_delta(delta: dict[str, Any], project_dir: str | None = None) -> dict[str, Any]:
    override = delta.get("override")
    waiver_artifact = delta.get("waiver_artifact")
    if _has_override(override):
        return {
            "verdict": "pass",
            "reasons": [],
            "flags": ["override_present"],
        }

    old_tests = _normalize_tests(delta.get("old_tests"))
    new_tests = _normalize_tests(delta.get("new_tests"))
    touched_paths = _normalize_paths(delta.get("touched_paths"))
    selectors = _normalize_string_list(delta.get("tests"))

    lock_payload: dict[str, Any] | None = None
    lock_id = str(delta.get("lock_id", "")).strip()
    if lock_id:
        if project_dir:
            lock_payload = _load_lock_payload_from_project(project_dir, lock_id)
        else:
            lock_payload = _load_lock_payload(lock_id)
        if lock_payload is None:
            return {
                "verdict": "fail",
                "reasons": [f"missing lock state for lock_id '{lock_id}'"],
                "flags": ["missing_lock_state"],
            }

    if lock_payload is not None:
        contract_reasons, contract_flags = _evaluate_locked_contract(
            lock_payload=lock_payload,
            selectors=selectors,
            old_tests=old_tests,
            new_tests=new_tests,
            touched_paths=touched_paths,
            project_dir=project_dir,
        )
        if contract_reasons and not _has_waiver_artifact(waiver_artifact):
            unique_flags = list(dict.fromkeys(contract_flags))
            return {
                "verdict": "fail",
                "reasons": contract_reasons,
                "flags": unique_flags,
            }
        if contract_reasons and _has_waiver_artifact(waiver_artifact):
            return {
                "verdict": "pass",
                "reasons": [],
                "flags": ["waiver_artifact_present"],
            }

    old_by_name = {item["name"]: item for item in old_tests}
    reasons: list[str] = []
    flags: list[str] = []

    for new_test in new_tests:
        name = new_test["name"]
        old_test = old_by_name.get(name)
        if not old_test:
            continue

        old_assertions = int(old_test.get("assertions", 0))
        new_assertions = int(new_test.get("assertions", 0))
        if new_assertions < old_assertions:
            flags.append("weakened_assertions")
            reasons.append(
                f"test '{name}' reduced assertions from {old_assertions} to {new_assertions}"
            )

        old_kind = str(old_test.get("kind", "")).strip().lower()
        new_kind = str(new_test.get("kind", "")).strip().lower()
        if old_kind == "integration" and new_kind == "mock":
            flags.append("integration_to_mock_downgrade")
            reasons.append(f"test '{name}' downgraded from integration to mock")

    if touched_paths and old_tests and not new_tests:
        flags.append("removed_touched_area_coverage")
        reasons.append("all tests for touched paths were removed from test delta")

    if touched_paths and new_tests and all(str(item.get("kind", "")).strip().lower() == "snapshot" for item in new_tests):
        flags.append("snapshot_only_refresh")
        reasons.append("delta contains only snapshot tests for touched paths")

    unique_flags = list(dict.fromkeys(flags))
    return {
        "verdict": "fail" if reasons else "pass",
        "reasons": reasons,
        "flags": unique_flags,
    }


def _has_override(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _has_waiver_artifact(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _normalize_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_tests(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    tests: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        assertions = item.get("assertions", 0)
        try:
            assertions_value = int(assertions)
        except (TypeError, ValueError):
            assertions_value = 0
        tests.append(
            {
                "name": name,
                "kind": str(item.get("kind", "")).strip(),
                "assertions": max(assertions_value, 0),
            }
        )
    return tests


def _normalize_assertion_metadata(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    metadata: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if "assertions" in normalized:
            try:
                normalized["assertions"] = max(int(normalized.get("assertions", 0)), 0)
            except (TypeError, ValueError):
                normalized["assertions"] = 0
        metadata.append(normalized)
    return metadata


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _extract_done_when_criteria(value: Any) -> list[str]:
    if isinstance(value, str):
        token = value.strip()
        return [token] if token else []
    if isinstance(value, list):
        return _normalize_string_list(value)
    if isinstance(value, dict):
        criteria = value.get("criteria")
        if isinstance(criteria, str):
            token = criteria.strip()
            return [token] if token else []
        if isinstance(criteria, list):
            return _normalize_string_list(criteria)
        summary = str(value.get("summary", "")).strip()
        return [summary] if summary else []
    return []


def _extract_done_when_run_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("run_id", "")).strip()
    return ""


def _extract_done_when_completion_state(metadata: dict[str, Any]) -> str:
    metadata_state = str(metadata.get("done_when_state", "")).strip().lower()
    if metadata_state in {"declared", "completed"}:
        return metadata_state

    done_when = metadata.get("done_when")
    if isinstance(done_when, dict):
        done_when_state = str(done_when.get("state", "")).strip().lower()
        if done_when_state in {"declared", "completed"}:
            return done_when_state
        if done_when.get("completed") is True:
            return "completed"
    return "declared"


def _selector_to_path(selector: str) -> str:
    return selector.split("::", 1)[0].strip()


def _hash_test_file(project_dir: Path, selector_path: str) -> str | None:
    candidate = (project_dir / selector_path).resolve()
    try:
        if not candidate.exists() or not candidate.is_file():
            return None
        return sha256(candidate.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_lock_payload(lock_id: str) -> dict[str, Any] | None:
    lock_path = Path(".omg") / "state" / "test-intent-lock" / f"{lock_id}.json"
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _load_lock_payload_from_project(project_dir: str, lock_id: str) -> dict[str, Any] | None:
    lock_path = Path(project_dir) / ".omg" / "state" / "test-intent-lock" / f"{lock_id}.json"
    return _load_lock_payload_from_path(lock_path)


def _load_lock_payload_from_path(lock_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _check_run_contract(payload: dict[str, Any], run_id: str) -> str | None:
    if not run_id:
        return None
    intent = payload.get("intent")
    if not isinstance(intent, dict):
        return "run_id_mismatch"
    intent_run_id = str(intent.get("run_id", "")).strip()
    if not intent_run_id:
        return "run_id_mismatch"
    if intent_run_id != run_id:
        return "run_id_mismatch"
    return None


def _evaluate_locked_contract(
    lock_payload: dict[str, Any],
    selectors: list[str],
    old_tests: list[dict[str, Any]],
    new_tests: list[dict[str, Any]],
    touched_paths: list[str],
    project_dir: str | None = None,
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    flags: list[str] = []
    locked_selectors = _normalize_string_list(lock_payload.get("test_selectors"))
    if not locked_selectors:
        intent = lock_payload.get("intent")
        if isinstance(intent, dict):
            locked_selectors = _normalize_string_list(intent.get("tests"))

    active_selectors = selectors
    if not active_selectors and new_tests:
        active_selectors = [item["name"] for item in new_tests if item.get("name")]

    if locked_selectors and active_selectors != locked_selectors:
        flags.append("locked_selectors_mismatch")
        reasons.append("locked test selectors changed from intent contract")

    test_file_hashes = lock_payload.get("test_file_hashes")
    if isinstance(test_file_hashes, dict):
        for selector_path, expected_hash in test_file_hashes.items():
            path_key = str(selector_path).strip()
            if not path_key:
                continue
            hash_project_dir = Path(project_dir) if project_dir else Path(".")
            current_hash = _hash_test_file(hash_project_dir, path_key)
            expected_hash_value = str(expected_hash).strip() if expected_hash is not None else None
            if expected_hash_value and current_hash is None:
                flags.append("locked_test_file_missing")
                reasons.append(f"locked test file '{path_key}' is missing")
            elif expected_hash_value and current_hash != expected_hash_value:
                flags.append("locked_test_file_changed")
                reasons.append(f"locked test file '{path_key}' hash mismatch")

    assertion_metadata = lock_payload.get("assertion_metadata")
    if isinstance(assertion_metadata, list) and assertion_metadata:
        new_by_name = {item["name"]: item for item in new_tests}
        for item in assertion_metadata:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            baseline = item.get("assertions")
            if baseline is None:
                continue
            try:
                baseline_count = max(int(baseline), 0)
            except (TypeError, ValueError):
                baseline_count = 0
            current = new_by_name.get(name)
            if current is None:
                continue
            current_assertions = max(int(current.get("assertions", 0)), 0)
            if current_assertions < baseline_count:
                flags.append("weakened_assertions")
                reasons.append(
                    f"test '{name}' reduced assertions from {baseline_count} to {current_assertions}"
                )

    old_by_name = {item["name"]: item for item in old_tests}
    for new_test in new_tests:
        name = new_test["name"]
        old_test = old_by_name.get(name)
        if not old_test:
            continue
        if int(new_test.get("assertions", 0)) < int(old_test.get("assertions", 0)):
            flags.append("weakened_assertions")
            reasons.append(
                f"test '{name}' reduced assertions from {old_test.get('assertions', 0)} to {new_test.get('assertions', 0)}"
            )

        old_kind = str(old_test.get("kind", "")).strip().lower()
        new_kind = str(new_test.get("kind", "")).strip().lower()
        if old_kind == "integration" and new_kind == "mock":
            flags.append("integration_to_mock_downgrade")
            reasons.append(f"test '{name}' downgraded from integration to mock")

    if touched_paths and old_tests and not new_tests:
        flags.append("removed_touched_area_coverage")
        reasons.append("all tests for touched paths were removed from test delta")

    if touched_paths and new_tests and all(str(item.get("kind", "")).strip().lower() == "snapshot" for item in new_tests):
        flags.append("snapshot_only_refresh")
        reasons.append("delta contains only snapshot tests for touched paths")

    return reasons, flags
