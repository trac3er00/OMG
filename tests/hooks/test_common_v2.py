#!/usr/bin/env python3
"""Unit tests for hooks/_common.py — verify _omg namespace (not _oal) for feature flags."""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# Add hooks to path
HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from _common import get_feature_flag


def test_get_feature_flag_reads_from_omg_namespace(monkeypatch):
    """Test that get_feature_flag reads from _omg namespace (not _oal)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", tmpdir)

        # Create settings.json with _omg namespace
        settings = {
            "_omg": {
                "features": {
                    "COST_TRACKING": True,
                    "MEMORY": False,
                    "PLANNING_ENFORCEMENT": True,
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        # Clear cache and env vars to force settings.json read
        import _common

        _common._FEATURE_CACHE.clear()
        monkeypatch.delenv("OMG_COST_TRACKING_ENABLED", raising=False)
        monkeypatch.delenv("OMG_MEMORY_ENABLED", raising=False)
        monkeypatch.delenv("OMG_PLANNING_ENFORCEMENT_ENABLED", raising=False)

        # Test: get_feature_flag should read from _omg.features
        assert get_feature_flag("COST_TRACKING") is True
        assert get_feature_flag("MEMORY") is False
        assert get_feature_flag("PLANNING_ENFORCEMENT") is True


def test_get_feature_flag_ignores_oal_namespace(monkeypatch):
    """Test that get_feature_flag does NOT read from legacy _oal namespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", tmpdir)

        # Create settings.json with ONLY _oal namespace (legacy, should be ignored)
        settings = {
            "_oal": {
                "features": {
                    "COST_TRACKING": True,
                    "MEMORY": True,
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        # Clear cache and env vars
        import _common

        _common._FEATURE_CACHE.clear()
        monkeypatch.delenv("OMG_COST_TRACKING_ENABLED", raising=False)
        monkeypatch.delenv("OMG_MEMORY_ENABLED", raising=False)

        # Test: get_feature_flag should NOT read from _oal, should return default
        assert get_feature_flag("COST_TRACKING", default=False) is False
        assert get_feature_flag("MEMORY", default=False) is False


def test_get_feature_flag_omg_takes_precedence(monkeypatch):
    """Test that _omg namespace is used when both _oal and _omg exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", tmpdir)

        # Create settings.json with BOTH namespaces (should use _omg)
        settings = {
            "_oal": {
                "features": {
                    "COST_TRACKING": False,
                    "MEMORY": False,
                }
            },
            "_omg": {
                "features": {
                    "COST_TRACKING": True,
                    "MEMORY": True,
                }
            },
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        # Clear cache and env vars
        import _common

        _common._FEATURE_CACHE.clear()
        monkeypatch.delenv("OMG_COST_TRACKING_ENABLED", raising=False)
        monkeypatch.delenv("OMG_MEMORY_ENABLED", raising=False)

        # Test: _omg values should be used, not _oal values
        assert get_feature_flag("COST_TRACKING") is True
        assert get_feature_flag("MEMORY") is True


def test_get_feature_flag_env_var_overrides_omg(monkeypatch):
    """Test that env vars still override _omg namespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", tmpdir)
        monkeypatch.setenv("OMG_COST_TRACKING_ENABLED", "0")

        # Create settings.json with _omg namespace
        settings = {
            "_omg": {
                "features": {
                    "COST_TRACKING": True,
                }
            }
        }
        settings_path = os.path.join(tmpdir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        # Clear cache
        import _common

        _common._FEATURE_CACHE.clear()

        # Test: env var should override _omg setting
        assert get_feature_flag("COST_TRACKING") is False


def test_bootstrap_runtime_paths_adds_active_project_dir(monkeypatch):
    """Installed hooks should import repo-local runtime packages via CLAUDE_PROJECT_DIR."""
    import _common

    with tempfile.TemporaryDirectory() as tmpdir:
        hook_anchor = Path(tmpdir) / ".claude" / "hooks" / "firewall.py"
        hook_anchor.parent.mkdir(parents=True, exist_ok=True)
        project_dir = Path(tmpdir) / "workspace"
        project_dir.mkdir()

        original_sys_path = list(sys.path)
        try:
            monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_dir))
            while str(project_dir) in sys.path:
                sys.path.remove(str(project_dir))

            _common.bootstrap_runtime_paths(str(hook_anchor))

            resolved_sys_path = {str(Path(path).resolve()) for path in sys.path}
            assert str(project_dir.resolve()) in resolved_sys_path
        finally:
            sys.path[:] = original_sys_path


def test_bootstrap_runtime_paths_exits_during_uninstall(tmp_path: Path, monkeypatch):
    import _common

    hook_anchor = tmp_path / ".claude" / "hooks" / "firewall.py"
    hook_anchor.parent.mkdir(parents=True, exist_ok=True)
    claude_dir = tmp_path / "home" / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / ".omg-uninstalling").write_text("uninstalling\n", encoding="utf-8")

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    try:
        _common.bootstrap_runtime_paths(str(hook_anchor))
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("bootstrap_runtime_paths should exit cleanly during uninstall")


def test_log_hook_error_rotates_under_lockfile(tmp_path: Path, monkeypatch):
    import _common

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "hook-errors.jsonl"
    ledger_path.write_text("x" * (101 * 1024), encoding="utf-8")

    _common.log_hook_error("firewall", RuntimeError("boom"))

    lock_path = ledger_dir / "hook-errors.jsonl.lock"
    archive_path = ledger_dir / "hook-errors.jsonl.1"
    assert lock_path.exists()
    assert archive_path.exists()

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["hook"] == "firewall"
    assert entry["error"] == "boom"


def test_should_skip_stop_hooks_ignores_user_controlled_context_markers(tmp_path: Path, monkeypatch):
    import _common

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(_common, "is_stop_block_loop", lambda *args, **kwargs: False)

    assert _common.should_skip_stop_hooks({"message": "context window exceeded"}) is False


def test_should_skip_stop_hooks_allows_context_limit_stop_reason(tmp_path: Path, monkeypatch):
    import _common

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(_common, "is_stop_block_loop", lambda *args, **kwargs: False)

    assert _common.should_skip_stop_hooks({"stop_reason": "context window exceeded"}) is True


def test_should_skip_stop_hooks_allows_context_limit_failure_reason(tmp_path: Path, monkeypatch):
    import _common

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(_common, "is_stop_block_loop", lambda *args, **kwargs: False)

    assert _common.should_skip_stop_hooks({"failure_reason": "context window exceeded"}) is True


def test_should_skip_stop_hooks_guard5_skips_after_recent_block(tmp_path: Path, monkeypatch):
    import _common

    tracker_path = tmp_path / ".omg" / "state" / "ledger" / ".stop-block-tracker.json"
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(
        json.dumps(
            {
                "ts": "2099-01-01T00:00:00+00:00",
                "count": 1,
                "session_id": "active-session",
                "reason": "quality_check",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_SESSION_ID", "active-session")
    monkeypatch.setattr(_common, "is_stop_block_loop", lambda *args, **kwargs: False)

    assert _common.should_skip_stop_hooks({}) is True


def test_record_stop_block_preserves_existing_session_when_current_unknown(tmp_path: Path, monkeypatch):
    import _common

    tracker_path = tmp_path / ".omg" / "state" / "ledger" / ".stop-block-tracker.json"
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(
        json.dumps(
            {
                "ts": "2099-01-01T00:00:00+00:00",
                "count": 1,
                "session_id": "persist-me",
                "reason": "quality_check",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("SESSION_ID", raising=False)
    monkeypatch.delenv("OMG_SESSION_ID", raising=False)

    _common.record_stop_block(project_dir=str(tmp_path), reason="unknown")

    state = json.loads(tracker_path.read_text(encoding="utf-8"))
    assert state["count"] == 2
    assert state["session_id"] == "persist-me"
    assert state["reason"] == "quality_check"


def test_record_stop_block_creates_tracker_parent_on_first_write(tmp_path: Path):
    import _common

    tracker_path = tmp_path / ".omg" / "state" / "ledger" / ".stop-block-tracker.json"

    _common.record_stop_block(
        project_dir=str(tmp_path),
        reason="quality_check",
        session_id="session-a",
    )

    assert tracker_path.exists()
    state = json.loads(tracker_path.read_text(encoding="utf-8"))
    assert state["count"] == 1
    assert state["session_id"] == "session-a"
    assert state["reason"] == "quality_check"


def test_record_stop_block_serializes_increment_under_lock(tmp_path: Path, monkeypatch):
    import _common

    tracker_path = tmp_path / ".omg" / "state" / "ledger" / ".stop-block-tracker.json"
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(
        json.dumps(
            {
                "ts": "2099-01-01T00:00:00+00:00",
                "count": 1,
                "session_id": "session-a",
                "reason": "quality_check",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_SESSION_ID", "session-a")

    original_atomic_json_write = _common.atomic_json_write
    first_write_started = threading.Event()
    release_first_write = threading.Event()
    write_calls = {"count": 0}

    def delayed_atomic_json_write(path, data):
        write_calls["count"] += 1
        if write_calls["count"] == 1:
            first_write_started.set()
            release_first_write.wait(timeout=2)
        return original_atomic_json_write(path, data)

    monkeypatch.setattr(_common, "atomic_json_write", delayed_atomic_json_write)

    def worker():
        _common.record_stop_block(
            project_dir=str(tmp_path),
            reason="quality_check",
            session_id="session-a",
        )

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    assert first_write_started.wait(timeout=1)
    second.start()
    time.sleep(0.1)
    release_first_write.set()
    first.join(timeout=2)
    second.join(timeout=2)

    state = json.loads(tracker_path.read_text(encoding="utf-8"))
    assert state["count"] == 3
