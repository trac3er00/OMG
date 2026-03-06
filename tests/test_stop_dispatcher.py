import json
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any


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
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_check_verification_blocks_without_verification(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_stop_ctx"]["recent_commands"] = []
    blocks = stop_dispatcher.check_verification(data, str(tmp_path))
    assert len(blocks) == 1
    assert "NO verification commands" in blocks[0]


def test_check_verification_blocks_when_provider_run_is_degraded(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_stop_ctx"]["recent_commands"] = ["python3 scripts/omg.py providers smoke --provider codex"]
    data["provider_execution"] = {
        "provider": "codex",
        "host_mode": "claude_dispatch",
        "smoke_status": "mcp_unreachable",
    }

    blocks = stop_dispatcher.check_verification(data, str(tmp_path))

    assert len(blocks) == 1
    assert "provider execution was degraded" in blocks[0].lower()


def test_check_verification_respects_feature_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: False)
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    blocks = stop_dispatcher.check_verification(data, str(tmp_path))
    assert blocks == []


def test_check_diff_budget_blocks_over_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)

    class R:
        def __init__(self, out):
            self.stdout = out

    outputs = iter(
        [
            R("a.py\nb.py\nc.py\nd.py\n"),
            R("100\t50\ta.py\n50\t20\tb.py\n"),
        ]
    )
    monkeypatch.setattr(stop_dispatcher.subprocess, "run", lambda *args, **kwargs: next(outputs))

    data = _base_data()
    blocks = stop_dispatcher.check_diff_budget(data, str(tmp_path))
    assert len(blocks) == 1
    assert "Diff exceeds budget" in blocks[0]


def test_check_recent_failures_blocks_last_three_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
    data = _base_data()
    data["_stop_ctx"]["recent_entries"] = [
        {"tool": "Bash", "command": "one", "exit_code": 1},
        {"tool": "Bash", "command": "two", "exit_code": 2},
        {"tool": "Bash", "command": "three", "exit_code": 3},
    ]
    blocks = stop_dispatcher.check_recent_failures(data, str(tmp_path))
    assert len(blocks) == 1
    assert "Last 3 commands ALL FAILED" in blocks[0]


def test_check_test_execution_blocks_when_tests_modified_without_test_run(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
    data = _base_data()
    data["_stop_ctx"]["has_material_writes"] = True
    data["_has_test"] = False
    data["_changed_files"] = ["tests/test_alpha.py"]
    blocks = stop_dispatcher.check_test_execution(data, str(tmp_path))
    assert len(blocks) == 1
    assert "test suite was never executed" in blocks[0]


def test_check_test_validator_coverage_blocks_missing_test_updates(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_changed_files"] = ["src/auth/service.py", "src/auth/controller.py"]
    blocks = stop_dispatcher.check_test_validator_coverage(data, str(tmp_path))
    assert len(blocks) == 1
    assert "TEST-VALIDATOR" in blocks[0]


def test_check_test_validator_coverage_allows_when_test_files_present(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
    data = _base_data()
    data["_stop_ctx"]["has_source_writes"] = True
    data["_changed_files"] = ["src/auth/service.py", "tests/test_auth_service.py"]
    blocks = stop_dispatcher.check_test_validator_coverage(data, str(tmp_path))
    assert blocks == []


def test_check_false_fix_blocks_non_source_only(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
    data = _base_data()
    data["_stop_ctx"]["has_material_writes"] = True
    data["_changed_files"] = ["tests/test_alpha.py", "scripts/run.sh"]
    blocks = stop_dispatcher.check_false_fix(data, str(tmp_path))
    assert len(blocks) == 1
    assert "FALSE FIX DETECTED" in blocks[0]


def test_check_write_failures_blocks_failed_write_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
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
    monkeypatch.setattr(stop_dispatcher, "get_feature_flag", lambda *_args, **_kwargs: True)
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


def test_stop_gate_wrapper_executes_dispatcher_guard():
    result = subprocess.run(
        [sys.executable, "hooks/stop-gate.py"],
        input=json.dumps({"stop_hook_active": True}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
