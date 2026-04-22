"""Tests for failure detection and steering responses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.failure_detector import detect_loop, detect_cost_spike, detect_stuck
from runtime.steering import handle_failure, STEERING_LOG_REL_PATH


class TestDetectLoop:
    """Tests for detect_loop function."""

    def test_detect_loop_true(self) -> None:
        """detect_loop returns True for repeated actions."""
        result = detect_loop(["a", "a", "a"])
        assert result is True, "Should detect 3 consecutive identical actions"

    def test_detect_loop_false(self) -> None:
        """detect_loop returns False for different actions."""
        result = detect_loop(["a", "b", "c"])
        assert result is False, "Should not detect loop with distinct actions"

    def test_detect_loop_threshold(self) -> None:
        """Threshold=2 triggers on 2 repeats."""
        result = detect_loop(["a", "a"], threshold=2)
        assert result is True, "Should detect with threshold=2"
        
        result = detect_loop(["a", "a"], threshold=3)
        assert result is False, "Should not detect with threshold=3"

    def test_detect_loop_empty_list(self) -> None:
        """Empty list returns False."""
        result = detect_loop([])
        assert result is False, "Empty list should not be a loop"

    def test_detect_loop_single_item(self) -> None:
        """Single item does not form a loop."""
        result = detect_loop(["only_one"])
        assert result is False, "Single item should not be a loop"


class TestDetectCostSpike:
    """Tests for detect_cost_spike function."""

    def test_detect_cost_spike_above_threshold(self) -> None:
        """Cost spike detected when current exceeds expected * multiplier."""
        result = detect_cost_spike(current_cost=10.0, expected_cost=4.0, multiplier=2.0)
        assert result is True, "10 >= 4*2 should be a spike"

    def test_detect_cost_spike_below_threshold(self) -> None:
        """No spike when current is below threshold."""
        result = detect_cost_spike(current_cost=5.0, expected_cost=4.0, multiplier=2.0)
        assert result is False, "5 < 8 should not be a spike"


class TestDetectStuck:
    """Tests for detect_stuck function."""

    def test_detect_stuck_flatlined(self) -> None:
        """Stuck detected when progress is identical."""
        result = detect_stuck([1, 1, 1, 1, 1], window=5)
        assert result is True, "All identical should be stuck"

    def test_detect_stuck_progressing(self) -> None:
        """Not stuck when progress varies."""
        result = detect_stuck([1, 2, 3, 4, 5], window=5)
        assert result is False, "Varying progress should not be stuck"


class TestHandleFailure:
    """Tests for handle_failure steering function."""

    def test_handle_failure_loop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Loop failure returns reroute action."""
        monkeypatch.chdir(tmp_path)
        
        result = handle_failure("loop", {})
        
        assert result["action"] == "reroute", "Loop should trigger reroute"
        assert "loop" in result["message"].lower(), "Message should mention loop"

    def test_handle_failure_cost_spike(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cost spike failure returns pause action."""
        monkeypatch.chdir(tmp_path)
        
        result = handle_failure("cost_spike", {})
        
        assert result["action"] == "pause", "Cost spike should trigger pause"
        assert "cost" in result["message"].lower(), "Message should mention cost"

    def test_handle_failure_stuck(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stuck failure returns escalate action."""
        monkeypatch.chdir(tmp_path)
        
        result = handle_failure("stuck", {})
        
        assert result["action"] == "escalate", "Stuck should trigger escalate"
        assert "progress" in result["message"].lower(), "Message should mention progress"

    def test_steering_logs_event(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify steering_log.jsonl is created after handling failure."""
        monkeypatch.chdir(tmp_path)
        
        handle_failure("loop", {"test_context": "value"})
        
        log_path = tmp_path / STEERING_LOG_REL_PATH
        assert log_path.exists(), "Steering log file should be created"
        
        log_content = log_path.read_text().strip()
        event = json.loads(log_content)
        
        assert "timestamp" in event, "Log should have timestamp"
        assert event["failure_type"] == "loop", "Log should record failure type"
        assert event["decision"]["action"] == "reroute", "Log should record decision"
        assert event["context"]["test_context"] == "value", "Log should record context"

    def test_handle_failure_unknown_type(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown failure type returns inspect action."""
        monkeypatch.chdir(tmp_path)
        
        result = handle_failure("unknown_failure", {})
        
        assert result["action"] == "inspect", "Unknown type should trigger inspect"
