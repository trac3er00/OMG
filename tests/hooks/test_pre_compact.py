import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "hooks" / "pre-compact.py"


def test_pre_compact_truncates_large_snapshot_file(tmp_path):
    state = tmp_path / ".omg" / "state"
    ledger = state / "ledger"
    ledger.mkdir(parents=True)

    (state / "profile.yaml").write_text("name: demo\n", encoding="utf-8")
    (ledger / "tool-ledger.jsonl").write_text("x" * 5000, encoding="utf-8")

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OMG_PRECOMPACT_MAX_SNAPSHOT_BYTES"] = "128"

    proc = subprocess.run(
        ["python3", str(SCRIPT)],
        input=json.dumps({}),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=env,
        check=False,
    )

    assert proc.returncode == 0

    snapshots_root = state / "snapshots"
    snapshots = sorted(p for p in snapshots_root.iterdir() if p.is_dir())
    assert snapshots, "Expected pre-compact to create a snapshot directory"

    snap_ledger = snapshots[-1] / "tool-ledger.jsonl"
    assert snap_ledger.exists()
    content = snap_ledger.read_text(encoding="utf-8")
    assert "[TRUNCATED by pre-compact:" in content
    assert snap_ledger.stat().st_size < 400
