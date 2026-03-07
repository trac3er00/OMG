"""Tests for legacy skill compatibility dispatcher."""
from __future__ import annotations

import json
from pathlib import Path

from runtime.compat import dispatch_compat_skill, list_compat_skills


ROOT = Path(__file__).resolve().parents[2]


def test_list_compat_skills_meets_standalone_contract():
    compat = list_compat_skills()
    assert len(compat) >= 30
    assert "omg-teams" in compat
    assert "pipeline" in compat
    assert "security-review" in compat
    assert "ccg" in compat
    assert "omg-superpowers" in compat
    assert "claude-flow" in compat
    assert "memsearch" in compat


def test_list_compat_skills_has_broad_legacy_alias_coverage():
    compat = set(list_compat_skills())
    assert len(compat) >= 30


def test_dispatch_representative_skills(tmp_path: Path):
    for skill in [
        "omg-teams",
        "ccg",
        "pipeline",
        "note",
        "omg-doctor",
        "security-review",
        "plan",
        "omg-superpowers",
        "claude-flow",
        "memsearch",
        "ralph-wiggum",
    ]:
        result = dispatch_compat_skill(skill=skill, problem=f"compat smoke {skill}", project_dir=str(tmp_path))
        assert result["schema"] == "OmgCompatResult"
        assert result["status"] == "ok", f"{skill} failed: {result}"


def test_dispatch_all_compat_skills(tmp_path: Path):
    for skill in list_compat_skills():
        result = dispatch_compat_skill(skill=skill, problem=f"compat full {skill}", project_dir=str(tmp_path))
        assert result["status"] == "ok", f"{skill} failed: {result}"


def test_contract_is_attached_and_has_core_fields(tmp_path: Path):
    result = dispatch_compat_skill(skill="omg-teams", problem="x", project_dir=str(tmp_path))
    contract = result["contract"]
    assert contract["skill"] == "omg-teams"
    assert contract["route"] == "teams"
    assert "inputs" in contract
    assert "outputs" in contract
    assert "side_effects" in contract
    assert contract["maturity"] in {"native", "bridge"}


def test_security_review_alias_routes_to_canonical_security_check(tmp_path: Path):
    target = tmp_path / "danger.py"
    target.write_text("import subprocess\nsubprocess.run('echo risky', shell=True)\n", encoding="utf-8")

    result = dispatch_compat_skill(
        skill="security-review",
        problem=str(tmp_path),
        project_dir=str(tmp_path),
    )
    assert result["status"] == "ok"
    assert result["contract"]["route"] == "security_check"
    assert result["result"]["schema"] == "SecurityCheckResult"
    assert result["result"]["summary"]["finding_count"] >= 1


def test_compat_setup_and_doctor_routes_create_bootstrap(tmp_path: Path):
    setup = dispatch_compat_skill(skill="omg-setup", problem="bootstrap", project_dir=str(tmp_path))
    assert setup["status"] == "ok"
    assert (tmp_path / ".omg" / "state" / "profile.yaml").exists()
    assert (tmp_path / ".omg" / "idea.yml").exists()
    assert (tmp_path / ".omg" / "policy.yaml").exists()

    doctor = dispatch_compat_skill(skill="omg-doctor", project_dir=str(tmp_path))
    assert doctor["status"] == "ok"
    snapshot = doctor["result"]
    assert snapshot["status"] in {"pass", "warn"}
    assert "checks" in snapshot


def test_project_session_manager_writes_session_state(tmp_path: Path):
    out = dispatch_compat_skill(skill="project-session-manager", problem="track session", project_dir=str(tmp_path))
    assert out["status"] == "ok"
    session_path = tmp_path / ".omg" / "state" / "session.json"
    assert session_path.exists()
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    assert isinstance(payload.get("entries"), list)
    assert payload["entries"], "session entries should not be empty"


def test_promoted_skills_report_native_maturity(tmp_path: Path):
    promoted = [
        "autopilot",
        "review",
        "release",
        "tdd",
        "plan",
        "ralph",
        "ultrawork",
        "ultraqa",
        "analyze",
        "build-fix",
        "learn-about-omg",
        "learner",
        "note",
        "project-session-manager",
        "sci-omg",
        "skill",
        "trace",
        "writer-memory",
    ]
    for skill in promoted:
        out = dispatch_compat_skill(skill=skill, problem=f"native check {skill}", project_dir=str(tmp_path))
        assert out["status"] == "ok"
        assert out["contract"]["maturity"] == "native"


def test_autopilot_creates_persistent_state(tmp_path: Path):
    out = dispatch_compat_skill(skill="autopilot", problem="keep iterating", project_dir=str(tmp_path))
    assert out["status"] == "ok"
    state = tmp_path / ".omg" / "state" / "persistent-mode.json"
    assert state.exists()
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["mode"] == "autopilot"
    assert payload["status"] == "active"


def test_review_route_returns_dual_track_synthesis(tmp_path: Path):
    out = dispatch_compat_skill(skill="review", problem="review auth", project_dir=str(tmp_path))
    assert out["status"] == "ok"
    assert out["routed_to"] == "codex+ccg"
    synthesis = out["result"]
    assert synthesis["schema"] == "ReviewSynthesis"
    assert "tracks" in synthesis
    assert "codex" in synthesis["tracks"]
    assert "ccg" in synthesis["tracks"]


def test_tdd_route_writes_red_green_refactor_checklist(tmp_path: Path):
    out = dispatch_compat_skill(skill="tdd", problem="tdd sample", project_dir=str(tmp_path))
    assert out["status"] == "ok"
    checklist = tmp_path / ".omg" / "state" / "_checklist.md"
    assert checklist.exists()
    content = checklist.read_text(encoding="utf-8").lower()
    assert "red" in content
    assert "green" in content
    assert "refactor" in content


def test_native_bridge_batch_writes_expected_artifacts(tmp_path: Path):
    build_fix = dispatch_compat_skill(skill="build-fix", problem="fix failing build", project_dir=str(tmp_path))
    assert build_fix["status"] == "ok"
    assert (tmp_path / ".omg" / "state" / "build-fix.md").exists()

    analyze = dispatch_compat_skill(skill="analyze", problem="analyze crash", project_dir=str(tmp_path))
    assert analyze["status"] == "ok"
    assert (tmp_path / ".omg" / "evidence" / "analysis-analyze.json").exists()

    learner = dispatch_compat_skill(skill="learner", problem="learn pattern", project_dir=str(tmp_path))
    assert learner["status"] == "ok"
    assert (tmp_path / ".omg" / "knowledge" / "learning" / "learner.md").exists()

    note = dispatch_compat_skill(skill="note", problem="remember this", project_dir=str(tmp_path))
    assert note["status"] == "ok"
    assert (tmp_path / ".omg" / "knowledge" / "notes.md").exists()

    writer = dispatch_compat_skill(skill="writer-memory", problem="draft memory", project_dir=str(tmp_path))
    assert writer["status"] == "ok"
    assert (tmp_path / ".omg" / "knowledge" / "writer-memory.md").exists()


def test_invalid_request_is_rejected_and_audited(tmp_path: Path):
    bad = dispatch_compat_skill(
        skill="omg-teams",
        problem="x",
        files=["../secrets.txt"],
        project_dir=str(tmp_path),
    )
    assert bad["status"] == "error"
    assert "Invalid request" in bad["findings"][0]

    audit = tmp_path / ".omg" / "state" / "ledger" / "omg-compat-audit.jsonl"
    assert audit.exists()
    lines = [ln for ln in audit.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "audit ledger should contain at least one event"
    assert (tmp_path / ".omg" / "state" / "ledger" / "compat-audit.jsonl").exists()


def test_invalid_request_rejects_absolute_like_file_paths(tmp_path: Path):
    for bad_path in [r"C:\secrets.txt", "~/secrets.txt", " notes.md "]:
        out = dispatch_compat_skill(
            skill="review",
            problem="x",
            files=[bad_path],
            project_dir=str(tmp_path),
        )
        assert out["status"] == "error"
        assert "Invalid request" in out["findings"][0]


def test_valid_dispatch_writes_request_audit_event(tmp_path: Path):
    ok = dispatch_compat_skill(skill="omg-teams", problem="audit ok", project_dir=str(tmp_path))
    assert ok["status"] == "ok"
    audit = tmp_path / ".omg" / "state" / "ledger" / "omg-compat-audit.jsonl"
    assert audit.exists()
    events = [json.loads(ln) for ln in audit.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert any(ev.get("event") == "compat_dispatch_request" for ev in events)
    assert any(ev.get("event") == "compat_dispatch" for ev in events)
