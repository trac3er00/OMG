"""Tests for FailureLearner — failure recording and pattern detection."""
from __future__ import annotations

import pytest

from claude_experimental.memory.failure_learning import FailureLearner

pytestmark = pytest.mark.experimental


class TestFailureLearner:
    def test_record_failure_and_suggest_fix(self, tmp_path):
        """Recorded failure is retrievable via suggest_fix."""
        fl = FailureLearner(db_path=str(tmp_path / "test.db"))

        mid = fl.record_failure(
            context="authentication middleware",
            error_type="TypeError",
            error_message="'NoneType' object is not callable",
        )
        assert mid > 0

        suggestions = fl.suggest_fix(
            error_type="TypeError",
            context="authentication",
        )
        assert len(suggestions) >= 1
        assert suggestions[0]["error_type"] == "TypeError"

    def test_get_failure_patterns(self, tmp_path):
        """Recurring failure patterns are detected."""
        fl = FailureLearner(db_path=str(tmp_path / "test.db"))

        fl.record_failure("api handler", "ConnectionError", "timeout")
        fl.record_failure("webhook", "ConnectionError", "refused")
        fl.record_failure("auth", "ValueError", "invalid token")

        patterns = fl.get_failure_patterns(min_occurrences=2)
        assert len(patterns) >= 1
        error_types = {p["error_type"] for p in patterns}
        assert "ConnectionError" in error_types

    def test_sanitize_trace(self):
        """Stack traces have file paths and line numbers stripped."""
        trace = (
            'File "/home/user/app/main.py", line 42, in process\n'
            "  result = compute()"
        )
        sanitized = FailureLearner._sanitize_trace(trace)
        assert "/home/user/app/" not in sanitized
        assert "main.py" in sanitized
        assert "line 42" not in sanitized
