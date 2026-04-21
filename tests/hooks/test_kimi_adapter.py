from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "hooks" / "kimi-adapter.py"


def _run_adapter(stdin_data: str) -> dict[str, str]:
    proc = subprocess.run(
        ["python3", str(HOOK)],
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=os.environ.copy(),
        check=False,
    )
    assert proc.returncode == 0
    stdout = (proc.stdout or "").strip()
    return json.loads(stdout) if stdout else {}


def test_pre_tool_use_safe_tool_allows() -> None:
    out = _run_adapter(
        json.dumps(
            {
                "event": "PreToolUse",
                "tool": "Read",
                "host": "kimi",
                "input": {"file_path": "README.md"},
            }
        )
    )
    assert out == {"decision": "allow"}


def test_pre_tool_use_dangerous_command_denies() -> None:
    out = _run_adapter(
        json.dumps(
            {
                "event": "PreToolUse",
                "tool": "Bash",
                "host": "kimi",
                "input": {"command": "rm -rf /"},
            }
        )
    )
    assert out["decision"] == "deny"
    assert "dangerous command blocked" in out["reason"]


def test_post_tool_use_allows() -> None:
    out = _run_adapter(
        json.dumps(
            {
                "event": "PostToolUse",
                "tool": "Write",
                "host": "kimi",
            }
        )
    )
    assert out == {"decision": "allow"}


def test_non_kimi_host_passthrough_allow() -> None:
    out = _run_adapter(
        json.dumps(
            {
                "event": "PreToolUse",
                "tool": "Bash",
                "host": "claude",
                "input": {"command": "rm -rf /"},
            }
        )
    )
    assert out == {"decision": "allow"}


def test_invalid_json_returns_graceful_error() -> None:
    out = _run_adapter("not-json")
    assert out["decision"] == "allow"
    assert out["error"] == "invalid JSON"
