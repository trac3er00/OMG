from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def lock_intent(project_dir: str, intent: dict[str, Any]) -> dict[str, Any]:
    lock_id = str(uuid4())
    lock_dir = Path(project_dir) / ".omg" / "state" / "test-intent-lock"
    lock_dir.mkdir(parents=True, exist_ok=True)

    lock_path = lock_dir / f"{lock_id}.json"
    payload = {"schema": "TestIntentLock", "lock_id": lock_id, "intent": intent}
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


def evaluate_test_delta(delta: dict[str, Any]) -> dict[str, Any]:
    override = delta.get("override")
    if _has_override(override):
        return {
            "verdict": "pass",
            "reasons": [],
            "flags": ["override_present"],
        }

    old_tests = _normalize_tests(delta.get("old_tests"))
    new_tests = _normalize_tests(delta.get("new_tests"))
    touched_paths = _normalize_paths(delta.get("touched_paths"))

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


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
