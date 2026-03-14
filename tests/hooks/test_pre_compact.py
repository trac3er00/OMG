import json
import os
import subprocess
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "hooks" / "pre-compact.py"


def _load_precompact_module():
    spec = importlib.util.spec_from_file_location("pre_compact_hook", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_host_aware_thresholds(monkeypatch):
    module = _load_precompact_module()
    monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-4-6")
    monkeypatch.delenv("OMG_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    info = module._host_aware_compaction_threshold({})

    assert info["model_id"] == "claude-opus-4-6"
    assert info["class_label"] == "1M-class"
    assert info["trigger_tokens"] == 150000


def test_conservative_fallback_threshold(monkeypatch):
    module = _load_precompact_module()
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("OMG_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    info = module._host_aware_compaction_threshold({})

    assert info["model_id"] == ""
    assert info["class_label"] == "128k-class"
    assert info["trigger_tokens"] == 80000


def test_host_aware_threshold_prefers_event_model_over_stale_env(monkeypatch):
    module = _load_precompact_module()
    monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-4-6")
    monkeypatch.delenv("OMG_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    switched = module._host_aware_compaction_threshold(
        {"model": {"id": "gemini-3-flash"}}
    )

    assert switched["model_id"] == "gemini-3-flash"
    assert switched["class_label"] == "200k-class"
    assert switched["trigger_tokens"] == 120000
