from __future__ import annotations

from importlib import import_module
import logging
from pathlib import Path

from runtime.worker_watchdog import WorkerWatchdog

detect_loop = import_module("runtime.loop_breaker").detect_loop


def _call(tool: str, **args: object) -> dict[str, object]:
    return {"tool": tool, "args": args}


def test_detects_repetition_for_three_identical_calls() -> None:
    history = [
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
    ]

    result = detect_loop(history)

    assert result["detected"] is True
    assert result["type"] == "repetition"
    assert result["history_analyzed"] == 3


def test_detects_oscillation_for_repeating_ab_pattern() -> None:
    history = [
        _call("read", file_path="runtime/a.py"),
        _call("grep", pattern="TODO", path="runtime"),
        _call("read", file_path="runtime/a.py"),
        _call("grep", pattern="TODO", path="runtime"),
    ]

    result = detect_loop(history)

    assert result["detected"] is True
    assert result["type"] == "oscillation"


def test_tdd_cycle_is_not_reported_as_loop() -> None:
    history = [
        _call(
            "Write",
            file_path="tests/runtime/test_loop_breaker.py",
            content="assert False\n",
        ),
        _call("Bash", command="pytest tests/runtime/test_loop_breaker.py"),
        _call(
            "Write",
            file_path="runtime/loop_breaker.py",
            content="def detect_loop():\n    pass\n",
        ),
        _call("Bash", command="pytest tests/runtime/test_loop_breaker.py"),
    ]

    result = detect_loop(history)

    assert result["detected"] is False
    assert result["type"] is None


def test_varied_work_across_different_files_is_not_a_loop() -> None:
    history = [
        _call("grep", pattern="WorkerWatchdog", path="runtime"),
        _call("read", file_path="runtime/worker_watchdog.py"),
        _call("write", file_path="runtime/loop_breaker.py", content="new impl"),
        _call("read", file_path="tests/runtime/test_loop_breaker.py"),
        _call(
            "write", file_path="tests/runtime/test_loop_breaker.py", content="new test"
        ),
    ]

    result = detect_loop(history)

    assert result["detected"] is False
    assert result["type"] is None


def test_detected_loop_returns_actionable_suggestion() -> None:
    history = [
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
    ]

    result = detect_loop(history)

    assert result["suggestion"] == "Try reading the error output more carefully"


def test_short_history_does_not_trigger_detection() -> None:
    history = [
        _call("read", file_path="runtime/worker_watchdog.py"),
        _call("grep", pattern="loop", path="runtime"),
    ]

    result = detect_loop(history)

    assert result["detected"] is False
    assert result["type"] is None
    assert result["history_analyzed"] == 2


def test_detects_stagnation_when_different_tools_keep_touching_same_file() -> None:
    history = [
        _call("read", file_path="runtime/worker_watchdog.py"),
        _call("grep", path="runtime/worker_watchdog.py", pattern="WorkerWatchdog"),
        _call("write", file_path="runtime/worker_watchdog.py", content="edit 1"),
        _call("lint", file_path="runtime/worker_watchdog.py"),
        _call("format", file_path="runtime/worker_watchdog.py"),
    ]

    result = detect_loop(history)

    assert result["detected"] is True
    assert result["type"] == "stagnation"
    assert result["suggestion"] == "Try a different file or ask for clarification"


def test_worker_watchdog_logs_loop_suggestions(caplog, tmp_path: Path) -> None:
    history = [
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
        _call("grep", pattern="loop", path="runtime/worker_watchdog.py"),
    ]
    watchdog = WorkerWatchdog(str(tmp_path))

    with caplog.at_level(logging.WARNING):
        result = watchdog.check_loop("run-loop", history)

    assert result["detected"] is True
    assert any(
        "Try reading the error output more carefully" in message
        for message in caplog.messages
    )
