"""Reusable helpers for hook regression tests."""
import json
import subprocess
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_hook_json(script_rel_path: str, payload: dict, env_overrides: dict = None):
    """Run a hook script with JSON payload on stdin, return parsed JSON output or None."""
    script = ROOT / script_rel_path
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    if env_overrides:
        env.update(env_overrides)

    proc = subprocess.run(
        ["python3", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    return json.loads(stdout) if stdout else None


def get_decision(output: dict):
    """Extract permissionDecision from hook output."""
    if not output:
        return None
    return (output.get("hookSpecificOutput") or {}).get("permissionDecision")


def make_bash_payload(command: str):
    """Create a standard Bash tool payload."""
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {},
    }


def make_file_payload(tool: str, file_path: str):
    """Create a Read/Write/Edit tool payload."""
    return {
        "tool_name": tool,
        "tool_input": {"file_path": file_path},
        "tool_response": {},
    }
