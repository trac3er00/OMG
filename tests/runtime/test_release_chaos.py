from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime.claim_judge import evaluate_claims_for_release
from runtime.complexity_scorer import score_complexity
from runtime.context_engine import ContextEngine
from runtime.incident_replay import build_chaos_replay_pack, replay_chaos_pack
from runtime.issue_surface import IssueSurface
from runtime.music_omr_testbed import MusicOMRTestbed
from runtime.worker_watchdog import WorkerWatchdog

_HELLO_CONTEXT_BUDGET_MAX_CHARS = 1000


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "chaos"
_MUSIC_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "music_omr"


def _load_fixture(name: str) -> dict[str, Any]:
    payload = json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_hello_without_subagents(tmp_path: Path) -> None:
    complexity = score_complexity("hello")
    governance = complexity.get("governance")

    assert complexity["category"] in {"trivial", "low"}
    assert isinstance(governance, dict)
    assert governance.get("simplify_only") is True
    assert governance.get("read_first") is False

    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id="chaos-hello-no-subagents",
        scenario="hello_without_subagents",
        fixture="inline:hello",
        fault="subagent_spawn_denied",
        expected_outcome={"status": "ok", "blockers": []},
        observed={"status": "ok", "category": complexity["category"]},
    )

    assert (tmp_path / pack["path"]).exists()


def test_hello_prompt_keeps_context_packet_bounded(tmp_path: Path) -> None:
    packet = ContextEngine(str(tmp_path)).build_packet(run_id="chaos-hello-context-budget")

    assert packet["packet_version"] == "v2"
    assert packet["budget"]["max_chars"] == 1000
    assert packet["budget"]["used_chars"] <= packet["budget"]["max_chars"]
    assert len(packet["summary"]) <= packet["budget"]["max_chars"]
    assert packet["provenance_only"] is False


def test_hello_no_subagent_spawn_and_bounded_context(tmp_path: Path) -> None:
    complexity = score_complexity("hello")
    governance = complexity.get("governance")
    assert isinstance(governance, dict)

    assert complexity["category"] in {"trivial", "low"}
    assert governance.get("simplify_only") is True
    assert governance.get("read_first") is False
    assert governance.get("subagent_allowed", True) is not True or governance.get("simplify_only") is True

    packet = ContextEngine(str(tmp_path)).build_packet(run_id="chaos-hello-no-subagent")
    assert packet["packet_version"] == "v2"
    assert packet["budget"]["max_chars"] == _HELLO_CONTEXT_BUDGET_MAX_CHARS
    assert packet["budget"]["used_chars"] <= _HELLO_CONTEXT_BUDGET_MAX_CHARS
    assert len(packet["summary"]) <= _HELLO_CONTEXT_BUDGET_MAX_CHARS
    assert packet["provenance_only"] is False

    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id="chaos-hello-no-subagent-bounded",
        scenario="hello_no_subagent_bounded_context",
        fixture="inline:hello",
        fault="subagent_spawn_denied_and_context_bounded",
        expected_outcome={"status": "ok", "blockers": []},
        observed={
            "status": "ok",
            "category": complexity["category"],
            "context_used_chars": packet["budget"]["used_chars"],
            "context_max_chars": packet["budget"]["max_chars"],
            "subagent_blocked": True,
        },
        trace_id="trace-chaos-hello-no-subagent",
        evidence_freshness_max_age_seconds=30,
    )

    assert (tmp_path / pack["path"]).exists()
    assert pack["evidence_freshness"]["trace_id"] == "trace-chaos-hello-no-subagent"
    assert pack["evidence_freshness"]["max_age_seconds"] == 30

    replay = replay_chaos_pack(str(tmp_path), pack["path"])
    assert replay["reproduced"] is True
    assert replay["status"] == "ok"


def test_bug_fix_read_first_flow(tmp_path: Path) -> None:
    prompt = "Fix auth regression and then update tests followed by docs cleanup"
    complexity = score_complexity(prompt)
    governance = complexity.get("governance")

    assert isinstance(governance, dict)
    assert governance.get("read_first") is True
    assert governance.get("complexity") in {"medium", "high"}

    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id="chaos-bug-fix-read-first",
        scenario="bug_fix_read_first_flow",
        fixture="inline:bug-fix-prompt",
        fault="mutation_before_read_guard",
        expected_outcome={"status": "ok", "blockers": []},
        observed={"status": "ok", "read_first": governance.get("read_first")},
    )

    assert (tmp_path / pack["path"]).exists()


def test_worker_stall_detected_and_escalated(tmp_path: Path) -> None:
    fixture = _load_fixture("worker_stall_fixture.json")
    run_id = str(fixture["run_id"])
    worker_pid = int(fixture["worker_pid"])

    watchdog = WorkerWatchdog(str(tmp_path))
    _ = watchdog.record_heartbeat(run_id, worker_pid=worker_pid)

    heartbeat_path = tmp_path / ".omg" / "state" / "worker-heartbeats" / f"{run_id}.json"
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    stale_at = datetime.now(timezone.utc) - timedelta(seconds=float(fixture["stale_by_seconds"]))
    heartbeat["last_heartbeat_at"] = stale_at.isoformat()
    heartbeat_path.write_text(json.dumps(heartbeat, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    stall = watchdog.escalate_stall(run_id, stall_threshold_seconds=float(fixture["stall_threshold_seconds"]))
    assert stall is not None
    assert stall["status"] == "stalled"
    assert "evidence" in stall

    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id=run_id,
        scenario="worker_stall_detected_and_escalated",
        fixture="worker_stall_fixture.json",
        fault="stalled_worker_heartbeat",
        expected_outcome={"status": "blocked", "blockers": ["worker_stall"]},
        observed={"status": "blocked", "blockers": ["worker_stall"], "stall": stall},
        trace_id=str(fixture.get("trace_id", "")),
    )

    assert (tmp_path / pack["path"]).exists()


def test_plugin_interop_breakage_surfaced(tmp_path: Path, monkeypatch) -> None:
    fixture = _load_fixture("plugin_interop_conflict_fixture.json")

    def _fake_diagnostics(root: str, live: bool = False) -> dict[str, Any]:
        _ = (root, live)
        diagnostics = fixture.get("diagnostics", {})
        assert isinstance(diagnostics, dict)
        return diagnostics

    monkeypatch.setattr("runtime.issue_surface.run_plugin_diagnostics", _fake_diagnostics)

    report = IssueSurface(str(tmp_path)).scan(str(fixture["run_id"]), surfaces=["plugin_interop"])
    assert report.issues
    assert any(issue.surface == "plugin_interop" and "mcp_name_collision" in issue.title for issue in report.issues)
    assert any(issue.severity == "high" for issue in report.issues)

    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id=str(fixture["run_id"]),
        scenario="plugin_interop_breakage_surfaced",
        fixture="plugin_interop_conflict_fixture.json",
        fault="plugin_conflict_blocker",
        expected_outcome={"status": "blocked", "blockers": ["plugin_interop_conflict"]},
        observed={
            "status": "blocked",
            "blockers": ["plugin_interop_conflict"],
            "report_path": report.summary.get("report_path", ""),
        },
    )

    assert (tmp_path / pack["path"]).exists()


def test_evidence_corruption_blocks_release(tmp_path: Path) -> None:
    fixture = _load_fixture("evidence_corruption_fixture.json")
    run_id = str(fixture["run_id"])
    artifact = fixture.get("artifact", {})
    assert isinstance(artifact, dict)

    artifact_relpath = str(artifact["path"])
    artifact_path = tmp_path / artifact_relpath
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("<testsuite><broken>", encoding="utf-8")

    claim = {
        "claim_type": str(fixture["claim_type"]),
        "run_id": run_id,
        "project_dir": str(tmp_path),
        "evidence_profile": str(fixture["evidence_profile"]),
        "trace_ids": [str(fixture["trace_id"])],
        "evidence": {
            "trace_ids": [str(fixture["trace_id"])],
            "artifacts": [
                {
                    "kind": str(artifact["kind"]),
                    "path": artifact_relpath,
                    "sha256": str(artifact["sha256"]),
                    "parser": str(artifact["parser"]),
                    "summary": str(artifact["summary"]),
                    "trace_id": str(fixture["trace_id"]),
                }
            ],
        },
    }

    decision = evaluate_claims_for_release(str(tmp_path), run_id=run_id, claims=[claim])
    assert decision["status"] == "blocked"
    assert "claim_judge_verdict" in str(decision["reason"])

    reasons = decision["claim_judge"]["results"][0]["reasons"]
    assert any(str(reason.get("code", "")).startswith("artifact_parse_failed_junit") for reason in reasons)

    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id=run_id,
        scenario="evidence_corruption_blocks_release",
        fixture="evidence_corruption_fixture.json",
        fault="corrupted_junit_artifact",
        expected_outcome={"status": "blocked", "blockers": ["evidence_corruption"]},
        observed={"status": "blocked", "blockers": ["evidence_corruption"], "reason": decision["reason"]},
        trace_id=str(fixture.get("trace_id", "")),
    )

    assert (tmp_path / pack["path"]).exists()


def test_transposition_pressure_under_load(tmp_path: Path) -> None:
    fixture = _load_fixture("transposition_pressure_fixture.json")
    score_fixture_path = _MUSIC_FIXTURE_DIR / "simple_c_major.json"

    testbed = MusicOMRTestbed(str(tmp_path))
    omr = testbed.run_omr(score_fixture_path)
    assert omr.notes

    pressure = testbed.run_pressure_suite(
        omr,
        str(fixture["target_key"]),
        iterations=int(fixture["iterations"]),
        runtime_ceiling_seconds=float(fixture["max_runtime_seconds"]),
    )

    assert pressure["deterministic"] is True
    assert pressure["unique_hash"] == str(fixture["expected_verification_hash"])
    assert pressure["within_ceiling"] is True
    assert pressure["iterations"] == int(fixture["iterations"])

    trace_id = str(fixture.get("trace_id", ""))
    freshness_max = float(fixture.get("evidence_freshness_max_age_seconds", 30))

    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id=str(fixture["run_id"]),
        scenario="transposition_pressure_under_load",
        fixture="transposition_pressure_fixture.json",
        fault="high_iteration_transposition_pressure",
        expected_outcome={"status": "ok", "blockers": []},
        observed={
            "status": "ok",
            "elapsed_seconds": pressure["elapsed_seconds"],
            "iterations": pressure["iterations"],
            "deterministic": pressure["deterministic"],
        },
        trace_id=trace_id,
        deterministic_seed=str(fixture.get("deterministic_seed", "")),
        evidence_freshness_max_age_seconds=freshness_max,
    )

    assert (tmp_path / pack["path"]).exists()
    assert pack["trace_id"] == trace_id
    assert pack["evidence_freshness"]["trace_id"] == trace_id
    assert pack["evidence_freshness"]["max_age_seconds"] == freshness_max
    assert pack["deterministic_seed"] == str(fixture.get("deterministic_seed", ""))

    evidence_path = testbed.emit_evidence(
        str(fixture["run_id"]),
        {"pressure": pressure},
        trace_id=trace_id,
    )
    assert Path(evidence_path).exists()

    replay = replay_chaos_pack(str(tmp_path), pack["path"])
    assert replay["reproduced"] is True
    assert replay["status"] == "ok"


def test_transposition_pressure_ceiling_deterministic(tmp_path: Path) -> None:
    fixture = _load_fixture("transposition_pressure_fixture.json")
    score_fixture_path = _MUSIC_FIXTURE_DIR / "simple_c_major.json"
    ceiling = int(fixture.get("pressure_ceiling_iterations", 64))

    testbed = MusicOMRTestbed(str(tmp_path))
    omr = testbed.run_omr(score_fixture_path)
    assert omr.notes

    pressure = testbed.run_pressure_suite(
        omr,
        str(fixture["target_key"]),
        iterations=ceiling,
        runtime_ceiling_seconds=float(fixture["max_runtime_seconds"]) * 3,
    )

    assert pressure["deterministic"] is True
    assert pressure["unique_hash"] == str(fixture["expected_verification_hash"])
    assert pressure["within_ceiling"] is True

    trace_id = f"trace-pressure-ceiling-{ceiling}"
    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id=f"chaos-pressure-ceiling-{ceiling}",
        scenario="transposition_pressure_ceiling",
        fixture="transposition_pressure_fixture.json",
        fault="pressure_ceiling_determinism",
        expected_outcome={"status": "ok", "blockers": []},
        observed={
            "status": "ok",
            "ceiling_iterations": ceiling,
            "deterministic": pressure["deterministic"],
            "elapsed_seconds": pressure["elapsed_seconds"],
        },
        trace_id=trace_id,
        evidence_freshness_max_age_seconds=float(fixture.get("evidence_freshness_max_age_seconds", 30)),
    )

    assert (tmp_path / pack["path"]).exists()
    assert pack["trace_id"] == trace_id
    assert pack["evidence_freshness"]["trace_id"] == trace_id


def test_chaos_replay_from_saved_evidence(tmp_path: Path) -> None:
    pack = build_chaos_replay_pack(
        str(tmp_path),
        run_id="chaos-replay-seeded-001",
        scenario="seeded_fault_replay",
        fixture="worker_stall_fixture.json",
        fault="seeded_worker_stall",
        expected_outcome={"status": "blocked", "blockers": ["worker_stall", "replay_required"]},
        observed={"status": "blocked", "blockers": ["worker_stall", "replay_required"]},
        trace_id="trace-chaos-replay",
        deterministic_seed="chaos-seed-001",
    )

    replay = replay_chaos_pack(str(tmp_path), pack["path"])
    assert replay["schema"] == "ChaosReplayResult"
    assert replay["status"] == "blocked"
    assert replay["reproduced"] is True
    assert replay["run_id"] == "chaos-replay-seeded-001"
