import json
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "stop_dispatcher",
    ROOT / "hooks" / "stop_dispatcher.py",
)
assert _SPEC and _SPEC.loader
stop_dispatcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stop_dispatcher)


def _base_data() -> dict[str, Any]:
    return {
        "_stop_ctx": {
            "recent_entries": [],
            "recent_commands": [],
            "has_source_writes": False,
            "has_material_writes": False,
        },
        "_stop_advisories": [],
    }


def test_stop_dispatcher_stop_hook_active_guard():
    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": True}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        check=False,
        timeout=20,
    )
    assert result.returncode == 0
    assert result.stdout == ""


# ─── Regression Guard Tests (named for QA scenario -k filters) ───────────────


def test_single_pass_blocking(tmp_path):
    """Regression guard: dispatcher emits at most one block decision per invocation.

    If Ralph loop blocks first, quality-check blocks must be suppressed.
    This test uses a specific name so the QA scenario `-k single_pass_blocking` hits it.
    """
    from datetime import datetime, timezone

    ralph_dir = tmp_path / ".omg" / "state"
    ralph_dir.mkdir(parents=True, exist_ok=True)
    (ralph_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 50,
                "original_prompt": "regression-guard",
            }
        )
    )
    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    (ledger_dir / "tool-ledger.jsonl").write_text(
        json.dumps({"ts": now, "tool": "Write", "file": "src/x.py"}) + "\n"
    )
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OMG_RALPH_LOOP_ENABLED"] = "1"
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")

    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": False}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0
    assert result.stdout.count('"decision"') == 1, "Expected exactly one block decision"


def test_dispatcher_watchdog_timeout():
    """Regression guard: _watchdog_check returns True when 90-second budget is exceeded.

    Named for QA scenario `-k dispatcher_watchdog_timeout`.
    """
    start_time = time.time() - 100  # 100 s ago — over the 90 s budget
    assert stop_dispatcher._watchdog_check(start_time) is True


def test_session_isolated_loop_tracker(tmp_path):
    """Regression guard: stale tracker from another session cannot suppress hooks.

    Named for QA scenario `-k session_isolated_loop_tracker`.
    """
    from datetime import datetime, timezone

    tracker_dir = tmp_path / ".omg" / "state" / "ledger"
    tracker_dir.mkdir(parents=True, exist_ok=True)
    (tracker_dir / ".stop-block-tracker.json").write_text(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "count": 10,
                "session_id": "old-session-xyz",
                "reason": "quality_check",
            }
        )
    )
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["CLAUDE_SESSION_ID"] = "new-session-abc"
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")

    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": False}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0
    assert "Guard 4 triggered" not in result.stderr, (
        "Cross-session stale tracker incorrectly suppressed hooks"
    )


def test_check_verification_blocks_without_verification(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_stop_ctx"]["recent_commands"] = []
    blocks = stop_dispatcher.check_verification(data, str(tmp_path))
    assert len(blocks) == 1
    assert "NO verification commands" in blocks[0]


def test_check_verification_respects_feature_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: False
    )
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    blocks = stop_dispatcher.check_verification(data, str(tmp_path))
    assert blocks == []


def test_check_diff_budget_blocks_over_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )

    class R:
        def __init__(self, out):
            self.stdout = out
            self.stderr = ""
            self.returncode = 0

    outputs = iter(
        [
            R("a.py\nb.py\nc.py\nd.py\n"),
            R("100\t50\ta.py\n50\t20\tb.py\n"),
        ]
    )
    monkeypatch.setattr(
        stop_dispatcher.subprocess, "run", lambda *args, **kwargs: next(outputs)
    )

    data = _base_data()
    blocks = stop_dispatcher.check_diff_budget(data, str(tmp_path))
    assert len(blocks) == 1
    assert "Diff exceeds budget" in blocks[0]


def test_check_recent_failures_blocks_last_three_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    data = _base_data()
    data["_stop_ctx"]["recent_entries"] = [
        {"tool": "Bash", "command": "one", "exit_code": 1},
        {"tool": "Bash", "command": "two", "exit_code": 2},
        {"tool": "Bash", "command": "three", "exit_code": 3},
    ]
    blocks = stop_dispatcher.check_recent_failures(data, str(tmp_path))
    assert len(blocks) == 1
    assert "Last 3 commands ALL FAILED" in blocks[0]


def test_check_test_execution_blocks_when_tests_modified_without_test_run(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    data = _base_data()
    data["_stop_ctx"]["has_material_writes"] = True
    data["_has_test"] = False
    data["_changed_files"] = ["tests/test_alpha.py"]
    blocks = stop_dispatcher.check_test_execution(data, str(tmp_path))
    assert len(blocks) == 1
    assert "test suite was never executed" in blocks[0]


def test_check_test_validator_coverage_blocks_missing_test_updates(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_changed_files"] = ["src/auth/service.py", "src/auth/controller.py"]
    blocks = stop_dispatcher.check_test_validator_coverage(data, str(tmp_path))
    assert len(blocks) == 1
    assert "TEST-VALIDATOR" in blocks[0]


def test_check_test_validator_coverage_allows_when_test_files_present(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_changed_files"] = ["src/auth/service.py", "tests/test_auth_service.py"]
    blocks = stop_dispatcher.check_test_validator_coverage(data, str(tmp_path))
    assert blocks == []


def test_check_false_fix_blocks_non_source_only(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    data = _base_data()
    data["_stop_ctx"]["has_material_writes"] = True
    data["_changed_files"] = ["tests/test_alpha.py", "scripts/run.sh"]
    blocks = stop_dispatcher.check_false_fix(data, str(tmp_path))
    assert len(blocks) == 1
    assert "FALSE FIX DETECTED" in blocks[0]


def test_check_write_failures_blocks_failed_write_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    data = _base_data()
    data["_stop_ctx"]["has_material_writes"] = True
    data["_stop_ctx"]["recent_entries"] = [
        {"tool": "Write", "file": "src/app.py", "success": True},
        {"tool": "Write", "file": "src/bad.py", "success": False},
    ]
    blocks = stop_dispatcher.check_write_failures(data, str(tmp_path))
    assert len(blocks) == 1
    assert "WRITE/EDIT FAILURE DETECTED" in blocks[0]
    assert "src/bad.py" in blocks[0]


def test_check_simplifier_emits_stderr_advisory(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    # Create a file with high comment ratio (>40%)
    sloppy = tmp_path / "sloppy.py"
    sloppy.write_text(
        "# comment 1\n# comment 2\n# comment 3\n"
        "# comment 4\n# comment 5\nx = 1\ny = 2\n"
    )
    data = _base_data()
    data["_stop_ctx"]["source_write_entries"] = [
        {"tool": "Write", "file": str(sloppy)},
    ]
    result = stop_dispatcher.check_simplifier(data, str(tmp_path))
    assert result == []  # Never blocks
    captured = capsys.readouterr()
    assert "@simplifier" in captured.err
    assert "comment lines" in captured.err


def test_check_tdd_proof_chain_blocks_missing_lock_in_strict_mode(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        stop_dispatcher, "resolve_current_run_id", lambda **_kwargs: "run-123"
    )
    monkeypatch.setattr(
        stop_dispatcher.test_intent_lock,
        "verify_lock",
        lambda *_args, **_kwargs: {
            "status": "missing_lock",
            "reason": "no_active_test_intent_lock",
            "lock_id": None,
        },
    )

    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_test_delta"] = {"flags": []}
    blocks = stop_dispatcher.check_tdd_proof_chain(data, str(tmp_path))

    assert len(blocks) == 1
    block_obj = json.loads(blocks[0])
    assert block_obj["status"] == "blocked"
    assert block_obj["reason"].startswith("tdd_proof_chain_incomplete")


def test_check_tdd_proof_chain_blocks_weakened_assertions_without_waiver(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        stop_dispatcher, "resolve_current_run_id", lambda **_kwargs: "run-123"
    )
    monkeypatch.setattr(
        stop_dispatcher.test_intent_lock,
        "verify_lock",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "reason": "active_test_intent_lock",
            "lock_id": "lock-1",
        },
    )

    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_test_delta"] = {"flags": ["weakened_assertions"], "waiver_artifact": {}}
    blocks = stop_dispatcher.check_tdd_proof_chain(data, str(tmp_path))

    assert len(blocks) == 1
    block_obj = json.loads(blocks[0])
    assert block_obj["status"] == "blocked"
    assert block_obj["reason"].startswith("tdd_proof_chain_incomplete")


def test_single_pass_ralph_blocks_prevent_quality_blocks(tmp_path):
    """Only one block decision is emitted — ralph blocks first, quality checks skipped."""
    from datetime import datetime, timezone

    # Ralph state: active
    ralph_dir = tmp_path / ".omg" / "state"
    ralph_dir.mkdir(parents=True, exist_ok=True)
    (ralph_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 50,
                "original_prompt": "test single-pass",
            }
        )
    )

    # Ledger: source file write without any verification (would trigger quality check)
    ledger_dir = tmp_path / ".omg" / "state" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    (ledger_dir / "tool-ledger.jsonl").write_text(
        json.dumps({"ts": now, "tool": "Write", "file": "src/app.py"}) + "\n"
    )

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OMG_RALPH_LOOP_ENABLED"] = "1"
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")

    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": False}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "test single-pass" in output["reason"]
    # Single-pass guarantee: only one block decision emitted
    assert result.stdout.count('"decision"') == 1


def test_ralph_blocks_bypass_mode(tmp_path):
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 10,
                "original_prompt": "bypass check",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError, match="Ralph loop cannot run with bypass mode active"
    ):
        stop_dispatcher.check_ralph_loop(
            str(tmp_path), {"permission_mode": "bypassPermissions"}
        )


def test_ralph_approval_gate_fires(tmp_path, monkeypatch):
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 10,
                "original_prompt": "approval check",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stop_dispatcher,
        "get_feature_flag",
        lambda name, default=True: name in {"ralph_loop", "ralph_approval_gate"},
    )
    monkeypatch.setattr(stop_dispatcher, "_is_interactive_session", lambda: False)

    block_reasons, advisories, is_question = stop_dispatcher.check_ralph_loop(
        str(tmp_path),
        {
            "tool_use_results": [
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "rm -f tmp.txt"},
                }
            ]
        },
    )

    assert advisories == []
    assert is_question is False
    assert len(block_reasons) == 1
    assert "Ralph approval gate denied destructive action" in block_reasons[0]


def test_ralph_pre_approval_respected(tmp_path, monkeypatch):
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 10,
                "original_prompt": "preapproval check",
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "ralph-approvals.json").write_text(
        json.dumps({"approved_actions": ["Bash:rm -f tmp.txt"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stop_dispatcher,
        "get_feature_flag",
        lambda name, default=True: name in {"ralph_loop", "ralph_approval_gate"},
    )
    monkeypatch.setattr(stop_dispatcher, "_is_interactive_session", lambda: False)

    block_reasons, advisories, is_question = stop_dispatcher.check_ralph_loop(
        str(tmp_path),
        {
            "tool_use_results": [
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "rm -f tmp.txt"},
                }
            ]
        },
    )

    assert advisories == []
    assert is_question is False
    assert len(block_reasons) == 1
    assert "approval gate denied" not in block_reasons[0].lower()


def test_watchdog_check_detects_timeout():
    """_watchdog_check returns True when wall-clock budget is exceeded."""
    start_time = time.time() - 100  # 100 seconds ago (>90s budget)
    assert stop_dispatcher._watchdog_check(start_time) is True


def test_watchdog_check_allows_within_budget():
    """_watchdog_check returns False within budget."""
    start_time = time.time()  # just now
    assert stop_dispatcher._watchdog_check(start_time) is False


def test_session_isolated_tracker_does_not_suppress_hooks(tmp_path):
    """Stale tracker from session A should not suppress hooks for session B."""
    from datetime import datetime, timezone

    # Write a tracker file with session A, high count (above threshold)
    tracker_dir = tmp_path / ".omg" / "state" / "ledger"
    tracker_dir.mkdir(parents=True, exist_ok=True)
    (tracker_dir / ".stop-block-tracker.json").write_text(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "count": 10,
                "session_id": "session-A",
                "reason": "quality_check",
            }
        )
    )

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["CLAUDE_SESSION_ID"] = "session-B"
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")

    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": False}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0
    # Guard 4 should NOT trigger for a different session
    assert "Guard 4 triggered" not in result.stderr


def test_stop_gate_wrapper_executes_dispatcher_guard():
    result = subprocess.run(
        [sys.executable, "hooks/stop-gate.py"],
        input=json.dumps({"stop_hook_active": True}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        check=False,
        timeout=20,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_current_turn_source_writes_false_when_no_tool_results(tmp_path):
    ctx = stop_dispatcher._build_context(str(tmp_path), stop_payload={})
    assert ctx["current_turn_has_source_writes"] is False
    assert ctx["current_turn_source_write_entries"] == []


def test_current_turn_source_writes_true_when_source_write_in_payload(tmp_path):
    payload = {
        "tool_use_results": [
            {
                "tool_name": "Write",
                "file": "src/foo.py",
            }
        ]
    }
    ctx = stop_dispatcher._build_context(str(tmp_path), stop_payload=payload)
    assert ctx["current_turn_has_source_writes"] is True
    assert len(ctx["current_turn_source_write_entries"]) == 1


def test_planning_gate_skips_read_only_turn(tmp_path):
    checklist = tmp_path / ".omg" / "state" / "_checklist.md"
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text("- [x] Done\n- [ ] Pending\n", encoding="utf-8")

    data = _base_data()
    data["_stop_ctx"]["current_turn_has_source_writes"] = False

    import importlib
    import unittest.mock as mock

    with mock.patch.object(stop_dispatcher, "get_feature_flag", return_value=True):
        with mock.patch.object(
            stop_dispatcher, "resolve_state_file", return_value=str(checklist)
        ):
            block_reasons, advisories = stop_dispatcher.check_planning_gate(
                str(tmp_path), data=data
            )

    assert block_reasons == []
    assert advisories == []


def test_planning_gate_demotes_stale_checklist_from_another_session(
    tmp_path, monkeypatch
):
    checklist = tmp_path / ".omg" / "state" / "_checklist.md"
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text("- [x] Done\n- [ ] Pending\n", encoding="utf-8")
    (checklist.parent / "_checklist.session").write_text(
        json.dumps(
            {
                "session_id": "old-session",
                "created_at": "2099-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        stop_dispatcher, "resolve_state_file", lambda *_args, **_kwargs: str(checklist)
    )
    monkeypatch.setenv("CLAUDE_SESSION_ID", "new-session")

    block_reasons, advisories = stop_dispatcher.check_planning_gate(
        str(tmp_path), data=_base_data()
    )

    assert block_reasons == []
    assert len(advisories) == 1
    assert "stale checklist" in advisories[0]
    assert "different session" in advisories[0]


def test_planning_gate_warns_when_checklist_complete_without_recent_activity(
    tmp_path, monkeypatch
):
    checklist = tmp_path / ".omg" / "state" / "_checklist.md"
    checklist.parent.mkdir(parents=True, exist_ok=True)
    checklist.write_text("- [x] One\n- [x] Two\n- [x] Three\n", encoding="utf-8")

    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        stop_dispatcher, "resolve_state_file", lambda *_args, **_kwargs: str(checklist)
    )

    block_reasons, advisories = stop_dispatcher.check_planning_gate(
        str(tmp_path), data=_base_data()
    )

    assert block_reasons == []
    assert len(advisories) == 1
    assert "no code changes or test runs found" in advisories[0]


def test_tdd_proof_chain_skips_read_only_turn(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )

    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_stop_ctx"]["current_turn_has_source_writes"] = False

    blocks = stop_dispatcher.check_tdd_proof_chain(data, str(tmp_path))
    assert blocks == []


def test_tdd_proof_chain_blocks_source_mutation(monkeypatch, tmp_path):
    monkeypatch.setenv("OMG_PROOF_CHAIN_STRICT", "1")
    monkeypatch.setattr(
        stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        stop_dispatcher, "resolve_current_run_id", lambda **_kwargs: "run-456"
    )
    monkeypatch.setattr(
        stop_dispatcher.test_intent_lock,
        "verify_lock",
        lambda *_args, **_kwargs: {
            "status": "missing_lock",
            "reason": "no_active_test_intent_lock",
            "lock_id": None,
        },
    )

    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_stop_ctx"]["current_turn_has_source_writes"] = True
    data["_test_delta"] = {"flags": []}

    blocks = stop_dispatcher.check_tdd_proof_chain(data, str(tmp_path))
    assert len(blocks) == 1
    block_obj = json.loads(blocks[0])
    assert block_obj["status"] == "blocked"
    assert block_obj["reason"].startswith("tdd_proof_chain_incomplete")


def test_ralph_converges_on_completed_task(monkeypatch, tmp_path):
    ralph_dir = tmp_path / ".omg" / "state"
    ralph_dir.mkdir(parents=True, exist_ok=True)
    ralph_path = ralph_dir / "ralph-loop.json"
    ralph_path.write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 50,
                "original_prompt": "finish task",
            }
        ),
        encoding="utf-8",
    )

    class _DiffResult:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(
        stop_dispatcher.subprocess, "run", lambda *args, **kwargs: _DiffResult()
    )

    def _feature(name, default=False):
        if name == "ralph_loop":
            return True
        if name == "ralph_convergence_detection":
            return True
        return default

    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", _feature)

    data = {"_stop_ctx": {"ledger_entries": []}}
    for _ in range(4):
        stop_dispatcher.check_ralph_loop(str(tmp_path), data)

    final_state = json.loads(ralph_path.read_text(encoding="utf-8"))
    assert final_state["iteration"] == 3
    assert final_state["active"] is False
    assert final_state["stop_reason"] == "converged_no_delta"


def test_ralph_respects_configurable_max(monkeypatch, tmp_path):
    ralph_dir = tmp_path / ".omg" / "state"
    ralph_dir.mkdir(parents=True, exist_ok=True)
    ralph_path = ralph_dir / "ralph-loop.json"
    ralph_path.write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 50,
                "original_prompt": "loop task",
            }
        ),
        encoding="utf-8",
    )
    (ralph_dir / "ralph-config.json").write_text(
        json.dumps({"max_iterations": 5}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stop_dispatcher,
        "get_feature_flag",
        lambda name, default=False: True if name == "ralph_loop" else default,
    )

    data = {"_stop_ctx": {"ledger_entries": []}}
    for _ in range(6):
        stop_dispatcher.check_ralph_loop(str(tmp_path), data)

    final_state = json.loads(ralph_path.read_text(encoding="utf-8"))
    assert final_state["iteration"] == 5
    assert final_state["active"] is False
    assert final_state["stop_reason"] == "max_iterations"


def test_ralph_stop_reason_field(monkeypatch, tmp_path):
    ralph_dir = tmp_path / ".omg" / "state"
    ralph_dir.mkdir(parents=True, exist_ok=True)
    ralph_path = ralph_dir / "ralph-loop.json"
    ralph_path.write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 1,
                "max_iterations": 50,
                "original_prompt": "done task",
                "completed": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        stop_dispatcher,
        "get_feature_flag",
        lambda name, default=False: True if name == "ralph_loop" else default,
    )

    stop_dispatcher.check_ralph_loop(
        str(tmp_path), {"_stop_ctx": {"ledger_entries": []}}
    )
    final_state = json.loads(ralph_path.read_text(encoding="utf-8"))
    assert final_state["active"] is False
    assert final_state["stop_reason"] == "completed"


def _ralph_flags(flag_name: str, default: bool = True) -> bool:
    if flag_name in {"ralph_loop", "ralph_rollback_manifests"}:
        return True
    return default


def test_rollback_manifest_created_per_iteration(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", _ralph_flags)

    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 5,
                "original_prompt": "rollback manifest test",
            }
        ),
        encoding="utf-8",
    )

    data = {
        "_stop_ctx": {
            "current_turn_source_write_entries": [{"file": "src/demo.py"}],
            "current_turn_run_id": "run-ralph-1",
        }
    }
    block_reasons, advisories, is_question = stop_dispatcher.check_ralph_loop(
        str(tmp_path), data
    )

    assert block_reasons
    assert advisories == []
    assert is_question is False
    manifest_path = tmp_path / ".omg" / "state" / "ralph-rollbacks" / "iteration-1.json"
    assert manifest_path.exists()


def test_rollback_manifest_schema(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", _ralph_flags)

    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 5,
                "original_prompt": "schema test",
            }
        ),
        encoding="utf-8",
    )
    data = {
        "_stop_ctx": {
            "current_turn_source_write_entries": [{"file": "src/schema.py"}],
            "current_turn_run_id": "run-ralph-schema",
        }
    }
    stop_dispatcher.check_ralph_loop(str(tmp_path), data)

    payload = json.loads(
        (
            tmp_path / ".omg" / "state" / "ralph-rollbacks" / "iteration-1.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["iteration"] == 1
    assert isinstance(payload["files_changed"], list)
    assert isinstance(payload["side_effects"], list)
    assert isinstance(payload["rollback_commands"], list)


def test_rollback_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", _ralph_flags)

    subprocess.run(
        ["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True
    )
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.txt"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "init",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 5,
                "original_prompt": "rollback exec",
            }
        ),
        encoding="utf-8",
    )

    rollbacks_dir = state_dir / "ralph-rollbacks"
    rollbacks_dir.mkdir(parents=True, exist_ok=True)
    baseline_snapshot = stop_dispatcher._capture_workspace_snapshot(str(tmp_path))
    (rollbacks_dir / ".snapshot.json").write_text(
        json.dumps({"captured_at": "now", "files": baseline_snapshot}),
        encoding="utf-8",
    )

    tracked.write_text("after\n", encoding="utf-8")
    data = {
        "_stop_ctx": {
            "current_turn_source_write_entries": [{"file": "tracked.txt"}],
            "current_turn_run_id": "run-ralph-exec",
        }
    }
    stop_dispatcher.check_ralph_loop(str(tmp_path), data)

    payload = json.loads(
        (rollbacks_dir / "iteration-1.json").read_text(encoding="utf-8")
    )
    assert payload["rollback_commands"], (
        "Expected rollback commands for tracked file modification"
    )
    for command in payload["rollback_commands"]:
        if command.startswith("#"):
            continue
        subprocess.run(
            command,
            cwd=tmp_path,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )

    assert tracked.read_text(encoding="utf-8") == "before\n"


def test_concurrent_ralph_blocked(tmp_path):
    """Second Ralph attempt is blocked when another live process holds the lock."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 50,
                "original_prompt": "concurrent test",
            }
        )
    )
    (state_dir / "ralph-loop.lock").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "acquired_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OMG_RALPH_LOOP_ENABLED"] = "1"
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")

    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": False}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "Ralph loop already active in another session" in output["reason"]
    assert f"PID: {os.getpid()}" in output["reason"]


def test_stale_lock_auto_broken(tmp_path):
    """Ralph starts normally when lock file references a dead PID."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 0,
                "max_iterations": 50,
                "original_prompt": "stale lock test",
            }
        )
    )
    dead_pid = 2147483647
    (state_dir / "ralph-loop.lock").write_text(
        json.dumps(
            {
                "pid": dead_pid,
                "acquired_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OMG_RALPH_LOOP_ENABLED"] = "1"
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")

    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": False}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "stale lock test" in output["reason"]
    assert "already active in another session" not in output["reason"]

    lock_data = json.loads((state_dir / "ralph-loop.lock").read_text())
    assert lock_data["pid"] != dead_pid


def test_lock_released_on_completion(tmp_path):
    """Lock file is removed when Ralph reaches max iterations."""
    state_dir = tmp_path / ".omg" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ralph-loop.json").write_text(
        json.dumps(
            {
                "active": True,
                "iteration": 50,
                "max_iterations": 50,
                "original_prompt": "lock release test",
            }
        )
    )

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OMG_RALPH_LOOP_ENABLED"] = "1"
    env.setdefault("OMG_PLANNING_ENFORCEMENT_ENABLED", "0")

    result = subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps({"stop_hook_active": False}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0
    assert not (state_dir / "ralph-loop.lock").exists()
