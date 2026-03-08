from __future__ import annotations

from runtime.router_critics import run_critics


def test_skeptic_fails_unsupported_claim_without_evidence(tmp_path):
    out = run_critics(
        candidate={"output": "trust me bro, implemented and tested everything"},
        context_packet={"summary": "claim without evidence", "artifact_pointers": []},
        project_dir=str(tmp_path),
    )

    assert out["skeptic"]["verdict"] == "fail"
    assert out["skeptic"]["findings"]
    assert isinstance(out["skeptic"]["confidence"], float)


def test_skeptic_passes_when_claims_have_evidence_pointers(tmp_path):
    out = run_critics(
        candidate={
            "output": "Implemented fix in runtime/team_router.py:188 and validated with python3 -m pytest tests/runtime/test_team_router.py -q"
        },
        context_packet={
            "summary": "router update",
            "artifact_pointers": ["runtime/team_router.py", ".sisyphus/evidence/task-12-equalizer.json"],
        },
        project_dir=str(tmp_path),
    )

    assert out["skeptic"]["verdict"] == "pass"


def test_hallucination_auditor_fails_unverifiable_references(tmp_path):
    out = run_critics(
        candidate={"output": "Updated ghost/path.py and function phantom_handler()"},
        context_packet={"summary": "known file runtime/team_router.py", "artifact_pointers": ["runtime/team_router.py"]},
        project_dir=str(tmp_path),
    )

    assert out["hallucination_auditor"]["verdict"] in {"warn", "fail"}
    assert out["hallucination_auditor"]["findings"]


def test_hallucination_auditor_passes_when_references_verifiable(tmp_path):
    source = tmp_path / "runtime" / "team_router.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def dispatch_team():\n    return {}\n", encoding="utf-8")

    out = run_critics(
        candidate={"output": "Patched runtime/team_router.py and function dispatch_team()"},
        context_packet={
            "summary": "function dispatch_team in runtime/team_router.py",
            "artifact_pointers": ["runtime/team_router.py"],
            "functions": ["dispatch_team"],
        },
        project_dir=str(tmp_path),
    )

    assert out["hallucination_auditor"]["verdict"] == "pass"


def test_run_critics_output_shape(tmp_path):
    out = run_critics(
        candidate={"output": "status update"},
        context_packet={"summary": "small bounded packet"},
        project_dir=str(tmp_path),
    )

    assert set(out.keys()) == {"skeptic", "hallucination_auditor"}
    for critic_name in out:
        critic = out[critic_name]
        assert set(critic.keys()) == {"verdict", "findings", "confidence"}
        assert critic["verdict"] in {"pass", "warn", "fail"}
