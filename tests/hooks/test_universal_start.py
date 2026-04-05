import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "hooks" / "universal" / "start.py"


def test_start_outputs_valid_timestamp() -> None:
    env = os.environ.copy()
    env["OMG_SESSION_ID"] = "session-test"
    env.pop("CLAUDE_CODE", None)
    env.pop("CODEX", None)
    env.pop("OPENCODE", None)
    env.pop("GEMINI", None)

    proc = subprocess.run(
        ["python3", str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert proc.returncode == 0
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines
    payload = json.loads(lines[-1])
    number_long = payload["timestamp"]["$date"]["$numberLong"]
    assert isinstance(number_long, str)
    assert number_long.isdigit()
    assert int(number_long) > 0
