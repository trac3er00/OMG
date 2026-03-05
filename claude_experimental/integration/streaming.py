"""claude_experimental.integration.streaming — Server-Sent Events (SSE) streaming for agent output."""
from __future__ import annotations

import threading
import uuid
from collections import deque
from typing import Generator, Optional


class SSEStream:
    """
    Server-Sent Events (SSE) streaming buffer for agent output.

    Provides in-memory buffering with backpressure handling and thread-safe access.
    Events are formatted as SSE-compliant strings and can be read with optional
    last_event_id filtering for resumable streams.

    Example:
        >>> stream = SSEStream(max_buffer=100)
        >>> stream.emit('content', 'Hello, world!')
        >>> for sse_line in stream.read():
        ...     print(sse_line)
        id: <uuid>
        event: content
        data: Hello, world!
        <BLANKLINE>
    """

    def __init__(self, max_buffer: int = 100) -> None:
        """
        Initialize SSE stream with bounded buffer.

        Args:
            max_buffer: Maximum number of events to buffer. Oldest events are
                       dropped when buffer overflows (FIFO backpressure).
        """
        from claude_experimental.integration import _require_enabled

        _require_enabled()

        self._max_buffer = max_buffer
        self._buffer: deque[dict[str, str]] = deque(maxlen=max_buffer)
        self._lock = threading.Lock()
        self._closed = False

    def emit(self, event_type: str, data: str, event_id: Optional[str] = None) -> None:
        """
        Emit an event to the stream buffer.

        Args:
            event_type: Event type (e.g., 'content', 'progress', 'error', 'complete').
            data: Event payload as string.
            event_id: Optional event ID. If not provided, a UUID is generated.

        Raises:
            RuntimeError: If stream is closed or feature flag is disabled.
        """
        from claude_experimental.integration import _require_enabled

        _require_enabled()

        if self._closed:
            raise RuntimeError("Cannot emit to closed stream")

        if event_id is None:
            event_id = str(uuid.uuid4())

        event = {"id": event_id, "event": event_type, "data": data}

        with self._lock:
            self._buffer.append(event)

    def read(self, last_event_id: Optional[str] = None) -> Generator[str, None, None]:
        """
        Read events from the stream as SSE-formatted strings.

        Yields events in FIFO order, optionally skipping events before a given
        last_event_id for resumable streams.

        Args:
            last_event_id: Optional event ID to resume from. Events with IDs
                          before this one are skipped.

        Yields:
            SSE-formatted event strings (including trailing blank line).

        Raises:
            RuntimeError: If feature flag is disabled.

        Example:
            >>> stream = SSEStream()
            >>> stream.emit('content', 'test')
            >>> for line in stream.read():
            ...     print(repr(line))
            'id: ...'
            'event: content'
            'data: test'
            ''
        """
        from claude_experimental.integration import _require_enabled

        _require_enabled()

        with self._lock:
            events = list(self._buffer)

        # Filter events if resuming from last_event_id
        if last_event_id is not None:
            found_index = -1
            for i, event in enumerate(events):
                if event["id"] == last_event_id:
                    found_index = i
                    break
            if found_index >= 0:
                events = events[found_index + 1 :]

        # Yield SSE-formatted events
        for event in events:
            yield f"id: {event['id']}"
            yield f"event: {event['event']}"
            yield f"data: {event['data']}"
            yield ""  # Blank line terminates event

    def close(self) -> None:
        """
        Signal that the stream is closed.

        Subsequent calls to emit() will raise RuntimeError.
        """
        with self._lock:
            self._closed = True
