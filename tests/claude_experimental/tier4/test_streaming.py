"""Tests for claude_experimental.integration.streaming — SSEStream."""
from __future__ import annotations

import threading

import pytest


@pytest.fixture(autouse=True)
def _enable_integration(monkeypatch):
    """Enable the ADVANCED_INTEGRATION feature flag for all tests."""
    monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "1")


@pytest.mark.experimental
class TestSSEStreamBasic:
    """Basic emit/read round-trip tests."""

    def test_emit_and_read_round_trip(self):
        """emit() followed by read() returns SSE-formatted event."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=100)
        stream.emit("content", "hello world")

        lines = list(stream.read())
        assert len(lines) == 4  # id, event, data, blank
        assert lines[0].startswith("id: ")
        assert lines[1] == "event: content"
        assert lines[2] == "data: hello world"
        assert lines[3] == ""

    def test_sse_format_compliance(self):
        """Events follow RFC 9110 SSE format: id/event/data/blank."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=10)
        stream.emit("progress", "50%", event_id="evt-001")

        lines = list(stream.read())
        assert lines[0] == "id: evt-001"
        assert lines[1] == "event: progress"
        assert lines[2] == "data: 50%"
        assert lines[3] == ""

    def test_multiple_events_fifo_order(self):
        """Multiple emitted events are read in FIFO order."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=100)
        stream.emit("content", "first", event_id="e1")
        stream.emit("content", "second", event_id="e2")
        stream.emit("content", "third", event_id="e3")

        lines = list(stream.read())
        # 3 events × 4 lines each = 12 lines
        assert len(lines) == 12
        assert lines[2] == "data: first"
        assert lines[6] == "data: second"
        assert lines[10] == "data: third"

    def test_custom_event_id(self):
        """Custom event_id is used instead of auto-generated UUID."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=10)
        stream.emit("error", "fail", event_id="custom-123")
        lines = list(stream.read())
        assert lines[0] == "id: custom-123"


@pytest.mark.experimental
class TestSSEStreamBackpressure:
    """Backpressure and buffer overflow tests."""

    def test_backpressure_drops_oldest(self):
        """Buffer overflow drops oldest events (deque maxlen)."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=100)
        for i in range(200):
            stream.emit("content", f"event-{i}", event_id=f"id-{i}")

        lines = list(stream.read())
        # 100 events × 4 lines = 400 lines
        assert len(lines) == 400
        # First event should be event-100 (oldest 100 dropped)
        assert lines[2] == "data: event-100"
        # Last event should be event-199
        assert lines[-2] == "data: event-199"


@pytest.mark.experimental
class TestSSEStreamResumable:
    """Resumable stream tests using last_event_id."""

    def test_last_event_id_filtering(self):
        """read(last_event_id=...) skips events before that ID."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=100)
        stream.emit("content", "a", event_id="e1")
        stream.emit("content", "b", event_id="e2")
        stream.emit("content", "c", event_id="e3")

        lines = list(stream.read(last_event_id="e1"))
        # Should only get e2 and e3 (2 events × 4 lines)
        assert len(lines) == 8
        assert lines[0] == "id: e2"
        assert lines[4] == "id: e3"

    def test_last_event_id_not_found_returns_all(self):
        """If last_event_id is not found, all events are returned."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=100)
        stream.emit("content", "a", event_id="e1")
        stream.emit("content", "b", event_id="e2")

        lines = list(stream.read(last_event_id="nonexistent"))
        assert len(lines) == 8  # All 2 events


@pytest.mark.experimental
class TestSSEStreamClose:
    """Close semantics tests."""

    def test_close_prevents_further_emit(self):
        """emit() raises RuntimeError after close()."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=10)
        stream.emit("content", "before close")
        stream.close()

        with pytest.raises(RuntimeError, match="closed"):
            stream.emit("content", "after close")

    def test_read_after_close_returns_existing(self):
        """read() still returns buffered events after close()."""
        from claude_experimental.integration.streaming import SSEStream

        stream = SSEStream(max_buffer=10)
        stream.emit("content", "still here", event_id="e1")
        stream.close()

        lines = list(stream.read())
        assert len(lines) == 4
        assert lines[2] == "data: still here"


@pytest.mark.experimental
class TestSSEStreamFeatureGate:
    """Feature flag gating tests."""

    def test_disabled_flag_constructor_raises(self, monkeypatch):
        """SSEStream constructor raises RuntimeError when flag is off."""
        from claude_experimental.integration.streaming import SSEStream

        monkeypatch.setenv("OMG_ADVANCED_INTEGRATION_ENABLED", "0")

        with pytest.raises(RuntimeError, match="disabled"):
            SSEStream(max_buffer=10)
