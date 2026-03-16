from __future__ import annotations

from importlib import import_module


_verdict_schema = import_module("runtime.verdict_schema")
action_required_verdict = _verdict_schema.action_required_verdict
normalize_verdict = _verdict_schema.normalize_verdict


def test_normalize_verdict_maps_legacy_verdict_to_status() -> None:
    normalized = normalize_verdict({"verdict": "pass"})

    assert normalized["status"] == "pass"
    assert normalized["verdict"] == "pass"


def test_action_required_verdict_sets_expected_status_and_blockers() -> None:
    receipt = action_required_verdict(["no_tests"])

    assert receipt["status"] == "action_required"
    assert receipt["verdict"] == "action_required"
    assert receipt["blockers"] == ["no_tests"]


def test_normalize_verdict_preserves_unknown_fields_in_metadata() -> None:
    normalized = normalize_verdict(
        {
            "status": "pass",
            "custom_signal": "keep-me",
            "nested": {"value": 1},
        }
    )

    assert normalized["metadata"]["custom_signal"] == "keep-me"
    assert normalized["metadata"]["nested"] == {"value": 1}


def test_action_required_is_generic_not_github_specific() -> None:
    normalized = normalize_verdict({"status": "action_required", "blockers": ["missing_evidence"]})

    assert normalized["status"] == "action_required"
    assert normalized["next_steps"] == []
    assert "review_event" not in normalized["metadata"]
