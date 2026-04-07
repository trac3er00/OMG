from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestMemoryTierEnum:
    def test_tier_enum_has_auto_micro_ship(self):
        from runtime.memory_schema import MemoryTier

        assert MemoryTier.AUTO == "auto"
        assert MemoryTier.MICRO == "micro"
        assert MemoryTier.SHIP == "ship"

    def test_tier_enum_members_are_complete(self):
        from runtime.memory_schema import MemoryTier

        names = {m.name for m in MemoryTier}
        assert names == {"AUTO", "MICRO", "SHIP"}

    def test_tier_values_are_lowercase_strings(self):
        from runtime.memory_schema import MemoryTier

        for member in MemoryTier:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)


class TestRetryBudgetExhaustion:
    def test_budget_exceeded_after_max_retries(self):
        from runtime.auto_resume import HandoffBudgetExceeded, RetryBudget

        budget = RetryBudget(max_retries=3)

        assert budget.increment(token_cost=100) is True
        assert budget.increment(token_cost=100) is True
        assert budget.increment(token_cost=100) is True
        assert budget.increment(token_cost=100) is False

    def test_resume_with_retries_raises_on_persistent_failure(self):
        from runtime.auto_resume import HandoffBudgetExceeded, resume_with_retries

        call_count = 0

        def always_fail(state: dict) -> dict:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("persistent failure")

        with pytest.raises(HandoffBudgetExceeded):
            resume_with_retries(
                {"key": "value"},
                handler=always_fail,
                max_retries=3,
            )

        assert call_count == 3

    def test_retry_budget_health_metrics(self):
        from runtime.auto_resume import RetryBudget

        budget = RetryBudget(max_retries=5)
        budget.increment(token_cost=200)
        budget.increment(token_cost=300)
        budget.success = True

        metrics = budget.health_metrics
        assert metrics["success"] is True
        assert metrics["attempt_count"] == 2
        assert metrics["max_retries"] == 5
        assert metrics["token_waste"] == 200
        assert metrics["success_rate"] == 0.5


class TestPhase0BaselineIntegrity:
    BASELINE_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        ".sisyphus",
        "evidence",
        "phase0-baseline.json",
    )

    def test_baseline_file_exists(self):
        assert os.path.isfile(self.BASELINE_PATH), (
            f"phase0-baseline.json not found at {self.BASELINE_PATH}"
        )

    def test_baseline_has_required_fields(self):
        with open(self.BASELINE_PATH) as f:
            baseline = json.load(f)

        required = [
            "ts_tests",
            "py_tests",
            "contract_valid",
            "versions",
            "test_intent_lock_id",
            "test_intent_lock_path",
        ]
        for field in required:
            assert field in baseline, f"Missing required field: {field}"

    def test_baseline_ts_tests_structure(self):
        with open(self.BASELINE_PATH) as f:
            baseline = json.load(f)

        ts = baseline["ts_tests"]
        assert ts["total"] >= 1320
        assert ts["fail"] == 0

    def test_baseline_py_tests_structure(self):
        with open(self.BASELINE_PATH) as f:
            baseline = json.load(f)

        py = baseline["py_tests"]
        assert py["pass"] >= 5326


class TestTestIntentLockReference:
    BASELINE_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        ".sisyphus",
        "evidence",
        "phase0-baseline.json",
    )

    def test_lock_path_exists_in_baseline(self):
        with open(self.BASELINE_PATH) as f:
            baseline = json.load(f)

        lock_path = baseline.get("test_intent_lock_path", "")
        assert lock_path, "test_intent_lock_path is empty"
        assert "test-intent-lock" in lock_path

    def test_lock_id_is_valid_uuid(self):
        with open(self.BASELINE_PATH) as f:
            baseline = json.load(f)

        lock_id = baseline.get("test_intent_lock_id", "")
        parts = lock_id.split("-")
        assert len(parts) == 5, f"Expected UUID format, got: {lock_id}"
