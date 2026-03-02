"""Tests for runtime dispatch orchestration."""

from runtime.dispatcher import dispatch_runtime


def test_dispatch_runtime_ok():
    result = dispatch_runtime("claude", {"goal": "ship feature"})
    assert result["status"] == "ok"
    assert result["runtime"] == "claude"
    assert "plan" in result
    assert "execution" in result
    assert "verification" in result
    assert "evidence" in result


def test_dispatch_runtime_not_found():
    result = dispatch_runtime("does-not-exist", {"goal": "x"})
    assert result["status"] == "error"
    assert result["error_code"] == "RUNTIME_NOT_FOUND"

