import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run_dispatcher(tmp_path: Path, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OAL_PLANNING_ENFORCEMENT_ENABLED"] = "1"
    return subprocess.run(
        [sys.executable, "hooks/stop_dispatcher.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
    )


def _write_checklist(tmp_path: Path, content: str) -> Path:
    path = tmp_path / ".oal" / "state" / "_checklist.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")
    return path


def test_incomplete_checklist_blocks(tmp_path: Path):
    _ = _write_checklist(tmp_path, "- [x] Done\n- [ ] Pending\n")
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "pending" in output["reason"].lower()


def test_complete_checklist_allows(tmp_path: Path):
    _ = _write_checklist(tmp_path, "- [x] Done 1\n- [x] Done 2\n")
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    assert result.stdout == ""


def test_blocked_items_not_counted_as_pending(tmp_path: Path):
    _ = _write_checklist(tmp_path, "- [x] Done\n- [!] Blocked\n")
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    assert result.stdout == ""


def test_no_checklist_allows_completion(tmp_path: Path):
    result = _run_dispatcher(tmp_path, {"stop_hook_active": False})
    assert result.returncode == 0
    assert result.stdout == ""
