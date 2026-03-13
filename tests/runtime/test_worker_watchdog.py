from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from runtime.worker_watchdog import WorkerWatchdog, get_worker_watchdog


# =============================================================================
# Heartbeat recording and retrieval
# =============================================================================


class TestHeartbeatRecording:
    def test_record_creates_heartbeat_file(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.record_heartbeat("run-hb1", worker_pid=12345)

        assert result["schema"] == "WorkerHeartbeat"
        assert result["run_id"] == "run-hb1"
        assert result["worker_pid"] == 12345
        assert result["status"] == "alive"
        assert result["heartbeat_count"] == 1

        hb_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / "run-hb1.json"
        assert hb_path.exists()
        persisted = json.loads(hb_path.read_text(encoding="utf-8"))
        assert persisted["run_id"] == "run-hb1"

    def test_record_increments_heartbeat_count(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("run-hb2", worker_pid=100)
        wd.record_heartbeat("run-hb2", worker_pid=100)
        result = wd.record_heartbeat("run-hb2", worker_pid=100)

        assert result["heartbeat_count"] == 3

    def test_read_heartbeat_returns_empty_for_missing(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        assert wd.read_heartbeat("nonexistent") == {}

    def test_read_heartbeat_returns_recorded_data(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("run-hb3", worker_pid=999, metadata={"phase": "build"})
        result = wd.read_heartbeat("run-hb3")

        assert result["worker_pid"] == 999
        assert result["metadata"]["phase"] == "build"

    def test_list_heartbeats(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("run-a")
        wd.record_heartbeat("run-b")
        wd.record_heartbeat("run-c")

        result = wd.list_heartbeats()
        run_ids = {r["run_id"] for r in result}
        assert run_ids == {"run-a", "run-b", "run-c"}

    def test_list_heartbeats_empty_when_no_dir(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        assert wd.list_heartbeats() == []


# =============================================================================
# Stall detection
# =============================================================================


class TestStallDetection:
    def test_check_stall_false_when_no_heartbeat(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        assert wd.check_stall("no-such-run") is False

    def test_check_stall_false_for_fresh_heartbeat(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("fresh-run", worker_pid=1)
        assert wd.check_stall("fresh-run", stall_threshold_seconds=60) is False

    def test_check_stall_true_for_expired_heartbeat(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("stale-run", worker_pid=1)

        hb_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / "stale-run.json"
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        data["last_heartbeat_at"] = old_time
        hb_path.write_text(json.dumps(data), encoding="utf-8")

        assert wd.check_stall("stale-run", stall_threshold_seconds=60) is True

    def test_check_stall_false_for_terminated_worker(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("term-run", worker_pid=1, status="terminated")

        hb_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / "term-run.json"
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        data["last_heartbeat_at"] = old_time
        hb_path.write_text(json.dumps(data), encoding="utf-8")

        assert wd.check_stall("term-run", stall_threshold_seconds=60) is False

    def test_get_stalled_workers_returns_stalled_only(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("active-run", worker_pid=1)
        wd.record_heartbeat("stalled-run", worker_pid=2)

        hb_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / "stalled-run.json"
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        data["last_heartbeat_at"] = old_time
        hb_path.write_text(json.dumps(data), encoding="utf-8")

        stalled = wd.get_stalled_workers(stall_threshold_seconds=60)
        assert len(stalled) == 1
        assert stalled[0]["run_id"] == "stalled-run"

    def test_escalate_stall_returns_none_when_not_stalled(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("ok-run", worker_pid=1)
        assert wd.escalate_stall("ok-run") is None

    def test_escalate_stall_marks_stalled_and_emits_evidence(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("esc-run", worker_pid=42)

        hb_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / "esc-run.json"
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        data["last_heartbeat_at"] = old_time
        hb_path.write_text(json.dumps(data), encoding="utf-8")

        result = wd.escalate_stall("esc-run", stall_threshold_seconds=60)
        assert result is not None
        assert result["status"] == "stalled"
        assert result["run_id"] == "esc-run"

        updated_hb = wd.read_heartbeat("esc-run")
        assert updated_hb["status"] == "stalled"

        replay_path = tmp_path / ".omg" / "evidence" / "subagents" / "esc-run-replay.json"
        assert replay_path.exists()


# =============================================================================
# Worker termination
# =============================================================================


class TestWorkerTermination:
    def test_terminate_nonexistent_process(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.terminate_worker("run-dead", 999999999)

        assert result["process_exited"] is True
        assert result["error"] is not None

    @patch("os.kill")
    def test_terminate_sends_sigterm_then_process_exits(self, mock_kill, tmp_path: Path) -> None:
        call_count = [0]

        def side_effect(pid, sig):
            call_count[0] += 1
            if sig == 0:
                if call_count[0] == 1:
                    return
                raise ProcessLookupError("gone")
            if sig == signal.SIGTERM:
                return

        mock_kill.side_effect = side_effect
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.terminate_worker("run-term", 12345, grace_seconds=0.2)

        assert result["sigterm_sent"] is True
        assert result["process_exited"] is True

    @patch("os.kill")
    def test_terminate_sends_sigkill_after_grace(self, mock_kill, tmp_path: Path) -> None:
        alive_until = [time.monotonic() + 0.5]

        def side_effect(pid, sig):
            if sig == 0:
                if time.monotonic() < alive_until[0]:
                    return
                raise ProcessLookupError("gone")
            return

        mock_kill.side_effect = side_effect
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.terminate_worker("run-kill", 12345, grace_seconds=0.2)

        assert result["sigterm_sent"] is True
        assert result["sigkill_sent"] is True
        assert result["process_exited"] is True


# =============================================================================
# Worktree cleanup
# =============================================================================


class TestWorktreeCleanup:
    def test_cleanup_nonexistent_worktree(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.cleanup_stale_worktree("no-wt")

        assert result["existed"] is False
        assert result["cleaned"] is False

    def test_cleanup_existing_worktree_fallback_rmtree(self, tmp_path: Path) -> None:
        wt_dir = tmp_path / ".omg" / "worktrees" / "wt-clean"
        wt_dir.mkdir(parents=True)
        (wt_dir / "file.txt").write_text("data")

        wd = WorkerWatchdog(str(tmp_path))

        with patch("subprocess.run", side_effect=OSError("no git")):
            result = wd.cleanup_stale_worktree("wt-clean")

        assert result["existed"] is True
        assert result["cleaned"] is True
        assert result["method"] == "shutil_rmtree"
        assert not wt_dir.exists()


# =============================================================================
# Replay evidence
# =============================================================================


class TestReplayEvidence:
    def test_emit_replay_evidence_writes_file(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.emit_replay_evidence("run-ev1", "test_cancellation")

        assert result["schema"] == "WorkerReplayEvidence"
        assert result["run_id"] == "run-ev1"
        assert result["reason"] == "test_cancellation"

        ev_path = tmp_path / ".omg" / "evidence" / "subagents" / "run-ev1-replay.json"
        assert ev_path.exists()
        persisted = json.loads(ev_path.read_text(encoding="utf-8"))
        assert persisted["schema"] == "WorkerReplayEvidence"

    def test_emit_replay_includes_termination_and_cleanup(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.emit_replay_evidence(
            "run-ev2",
            "full_cancel",
            termination={"sigterm_sent": True, "process_exited": True},
            cleanup={"cleaned": True, "method": "git_worktree_remove"},
        )

        assert result["termination"]["sigterm_sent"] is True
        assert result["cleanup"]["cleaned"] is True


# =============================================================================
# Composite cancel_and_cleanup
# =============================================================================


class TestCancelAndCleanup:
    @patch("os.kill")
    def test_cancel_and_cleanup_full_flow(self, mock_kill, tmp_path: Path) -> None:
        mock_kill.side_effect = ProcessLookupError("gone")

        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("run-cancel", worker_pid=111)

        result = wd.cancel_and_cleanup(
            "run-cancel",
            worker_pid=111,
            reason="user_cancelled",
        )

        assert result["status"] == "cancelled"
        assert result["termination"] is not None
        assert result["evidence"]["schema"] == "WorkerReplayEvidence"

        hb = wd.read_heartbeat("run-cancel")
        assert hb["status"] == "terminated"

    def test_cancel_and_cleanup_without_pid(self, tmp_path: Path) -> None:
        wd = WorkerWatchdog(str(tmp_path))
        result = wd.cancel_and_cleanup("run-nopid", reason="cleanup_only")

        assert result["status"] == "cancelled"
        assert result["termination"] is None
        assert result["evidence"]["schema"] == "WorkerReplayEvidence"


# =============================================================================
# Session health integration
# =============================================================================


class TestSessionHealthIntegration:
    def test_stalled_worker_triggers_warn_in_session_health(self, tmp_path: Path) -> None:
        from runtime.session_health import compute_session_health

        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("stall-health", worker_pid=1)

        hb_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / "stall-health.json"
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        data["last_heartbeat_at"] = old_time
        hb_path.write_text(json.dumps(data), encoding="utf-8")

        health = compute_session_health(str(tmp_path), run_id="stall-health")
        assert health["worker_stall"]["stalled_count"] >= 1
        assert health["sources"]["worker_heartbeats"] is True
        assert "warn" in health["action_recommendations"]

    def test_no_stall_keeps_session_healthy(self, tmp_path: Path) -> None:
        from runtime.session_health import compute_session_health

        health = compute_session_health(str(tmp_path), run_id="no-stall")
        assert health["worker_stall"]["stalled_count"] == 0
        assert health["sources"]["worker_heartbeats"] is False
        assert health["recommended_action"] == "continue"


# =============================================================================
# Background verification integration
# =============================================================================


class TestBackgroundVerificationIntegration:
    def test_check_worker_stalls_returns_summary(self, tmp_path: Path) -> None:
        from runtime.background_verification import check_worker_stalls

        wd = WorkerWatchdog(str(tmp_path))
        wd.record_heartbeat("bv-stall", worker_pid=1)

        hb_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / "bv-stall.json"
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        data["last_heartbeat_at"] = old_time
        hb_path.write_text(json.dumps(data), encoding="utf-8")

        result = check_worker_stalls(str(tmp_path))
        assert result["stalled_count"] >= 1
        assert "bv-stall" in result["stalled_run_ids"]

    def test_check_worker_stalls_no_stalls(self, tmp_path: Path) -> None:
        from runtime.background_verification import check_worker_stalls

        result = check_worker_stalls(str(tmp_path))
        assert result["stalled_count"] == 0
        assert result["stalled_run_ids"] == []


# =============================================================================
# Incident replay integration
# =============================================================================


class TestIncidentReplayIntegration:
    def test_build_worker_lifecycle_pack(self, tmp_path: Path) -> None:
        from runtime.incident_replay import build_worker_lifecycle_pack

        result = build_worker_lifecycle_pack(
            str(tmp_path),
            run_id="replay-run",
            event="cancel",
            heartbeat={"status": "stalled", "worker_pid": 42},
            termination={"sigterm_sent": True},
        )

        assert result["schema"] == "WorkerLifecycleReplayPack"
        assert result["run_id"] == "replay-run"
        assert result["event"] == "cancel"
        assert "path" in result

        incident_path = tmp_path / result["path"]
        assert incident_path.exists()


# =============================================================================
# Dispatcher cancel_job integration
# =============================================================================


class TestDispatcherCancelIntegration:
    @patch("runtime.subagent_dispatcher._persist_job")
    def test_cancel_running_job_emits_evidence(self, mock_persist, tmp_path: Path) -> None:
        from runtime.subagent_dispatcher import _jobs, _lock, cancel_job

        with _lock:
            _jobs.clear()

        with patch("runtime.subagent_dispatcher._get_project_dir", return_value=str(tmp_path)):
            _jobs["ev-cancel"] = {
                "job_id": "ev-cancel",
                "run_id": "run-ev-cancel",
                "agent_name": "test-agent",
                "status": "running",
                "worker_pid": None,
                "worktree": None,
            }

            result = cancel_job("ev-cancel")
            assert result is True
            assert _jobs["ev-cancel"]["status"] == "cancelled"

            replay_path = tmp_path / ".omg" / "evidence" / "subagents" / "run-ev-cancel-replay.json"
            assert replay_path.exists()

        with _lock:
            _jobs.clear()

    @patch("runtime.subagent_dispatcher._persist_job")
    def test_cancel_queued_job_succeeds(self, mock_persist, tmp_path: Path) -> None:
        from runtime.subagent_dispatcher import _jobs, _lock, cancel_job

        with _lock:
            _jobs.clear()

        with patch("runtime.subagent_dispatcher._get_project_dir", return_value=str(tmp_path)):
            _jobs["q-cancel"] = {
                "job_id": "q-cancel",
                "run_id": "run-q-cancel",
                "agent_name": "test-agent",
                "status": "queued",
                "worker_pid": None,
                "worktree": None,
            }

            result = cancel_job("q-cancel")
            assert result is True
            assert _jobs["q-cancel"]["status"] == "cancelled"

        with _lock:
            _jobs.clear()


# =============================================================================
# Factory function
# =============================================================================


class TestFactory:
    def test_get_worker_watchdog_returns_instance(self, tmp_path: Path) -> None:
        wd = get_worker_watchdog(str(tmp_path))
        assert isinstance(wd, WorkerWatchdog)
        assert wd.project_dir == Path(tmp_path)
