from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from runtime.forge_agents import (
    _check_backend_available,
    check_required_backends_satisfied,
    dispatch_specialists,
    get_specialist_registry,
    resolve_adapters,
    resolve_specialists,
)

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "scripts"


def _valid_job() -> dict[str, object]:
    return {
        "dataset": {
            "name": "vision-agent",
            "license": "apache-2.0",
            "source": "internal-curated",
        },
        "base_model": {
            "name": "distill-base-v1",
            "source": "approved-registry",
            "allow_distill": True,
        },
        "target_metric": 0.8,
        "simulated_metric": 0.9,
        "specialists": ["data-curator", "training-architect", "simulator-engineer"],
        "domain": "vision",
    }


def test_resolve_specialists_for_vision_agent_domain() -> None:
    specialists = resolve_specialists("vision-agent")
    assert specialists == ["data-curator", "training-architect", "simulator-engineer"]


def test_get_specialist_registry_contains_forge_specialists() -> None:
    registry = get_specialist_registry()
    assert "data-curator" in registry
    assert "training-architect" in registry
    assert "simulator-engineer" in registry
    assert "forge-cybersecurity" in registry
    assert "description" in registry["data-curator"]
    assert "capabilities" in registry["simulator-engineer"]


def test_resolve_specialists_for_cybersecurity_domain() -> None:
    specialists = resolve_specialists("cybersecurity")
    assert specialists == ["forge-cybersecurity"]


def test_dispatch_specialists_writes_evidence_and_returns_shape(tmp_path: Path) -> None:
    result = dispatch_specialists(_valid_job(), str(tmp_path))

    assert result["status"] == "ok"
    assert isinstance(result["run_id"], str)
    assert result["run_id"]
    assert result["specialists_dispatched"] == [
        "data-curator",
        "training-architect",
        "simulator-engineer",
    ]
    evidence_path = Path(str(result["evidence_path"]))
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "ForgeSpecialistDispatchEvidence"
    assert payload["run_id"] == result["run_id"]
    assert payload["contract"]["labs_only"] is True


def test_dispatch_cybersecurity_specialist_writes_proof_backed_evidence(tmp_path: Path) -> None:
    job = _valid_job()
    job["domain"] = "cybersecurity"
    job["specialists"] = ["forge-cybersecurity"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "ok"
    assert result["specialists_dispatched"] == ["forge-cybersecurity"]
    evidence_path = Path(str(result["evidence_path"]))
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["proof_backed"] is True
    assert payload["specialist"] == "forge-cybersecurity"


def test_dispatch_blocks_cybersecurity_specialist_for_non_labs_domain(tmp_path: Path) -> None:
    job = _valid_job()
    job["domain"] = "algorithms"
    job["specialists"] = ["training-architect", "forge-cybersecurity"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert result["reason"] == "invalid_specialist_domain_combination"


def test_dispatch_specialists_blocks_when_contract_mismatch(tmp_path: Path) -> None:
    job = _valid_job()
    job["specialists"] = ["data-curator"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert result["reason"] == "invalid_specialist_domain_combination"
    assert result["evidence_path"] == ""


def test_dispatch_invalid_domain_returns_combination_reason(tmp_path: Path) -> None:
    """Unknown domain + specialists → invalid_specialist_domain_combination."""
    job = _valid_job()
    job["domain"] = "nonexistent-domain"
    job["specialists"] = ["data-curator"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert result["reason"] == "invalid_specialist_domain_combination"


def test_dispatch_mismatched_specialists_returns_combination_reason(tmp_path: Path) -> None:
    """Specialists not valid for domain → invalid_specialist_domain_combination."""
    job = _valid_job()
    job["domain"] = "algorithms"
    job["specialists"] = ["simulator-engineer"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert result["reason"] == "invalid_specialist_domain_combination"


def test_dispatch_missing_required_specialists_returns_combination_reason(tmp_path: Path) -> None:
    """Requesting subset of required specialists → invalid_specialist_domain_combination."""
    job = _valid_job()
    job["domain"] = "vision"
    job["specialists"] = ["data-curator"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert result["reason"] == "invalid_specialist_domain_combination"


def test_dispatch_unknown_specialist_blocked(tmp_path: Path) -> None:
    """Unknown specialist names still blocked with specific reason."""
    job = _valid_job()
    job["domain"] = "vision"
    job["specialists"] = ["data-curator", "unknown-specialist", "training-architect", "simulator-engineer"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert "unknown" in str(result["reason"]).lower()


def test_dispatch_evidence_includes_proof_backed_fields(tmp_path: Path) -> None:
    """Dispatch evidence must contain proof-backed starter fields."""
    result = dispatch_specialists(_valid_job(), str(tmp_path))

    assert result["status"] == "ok"
    evidence_path = Path(str(result["evidence_path"]))
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert payload["proof_backed"] is True
    assert payload["contract"]["labs_only"] is True
    assert payload["specialist"] == "data-curator,training-architect,simulator-engineer"
    assert payload["domain"] == "vision"


def test_dispatch_evidence_includes_causal_chain_stub(tmp_path: Path) -> None:
    """Evidence must include causal chain fields for claim judge compat."""
    result = dispatch_specialists(_valid_job(), str(tmp_path))

    evidence_path = Path(str(result["evidence_path"]))
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert "causal_chain" in payload
    chain = payload["causal_chain"]
    assert "lock_id" in chain or "waiver_artifact_path" in chain


def test_dispatch_evidence_prefers_canonical_state_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RUN_ID", "state-run")

    defense_dir = tmp_path / ".omg" / "state" / "defense_state"
    defense_dir.mkdir(parents=True, exist_ok=True)
    canonical_defense_payload = {
        "schema": "DefenseState", "schema_version": "1.0.0",
        "run_id": "state-run", "status": "ok", "updated_at": "2026-03-08T00:00:00+00:00",
        "controls": {"firewall": "canonical"}, "findings": [],
    }
    latest_defense_payload = {
        "schema": "DefenseState", "schema_version": "1.0.0",
        "run_id": "legacy-run", "status": "ok", "updated_at": "2026-03-07T00:00:00+00:00",
        "controls": {"firewall": "legacy"}, "findings": [],
    }
    (defense_dir / "current.json").write_text(json.dumps(canonical_defense_payload), encoding="utf-8")
    (defense_dir / "latest.json").write_text(json.dumps(latest_defense_payload), encoding="utf-8")

    health_dir = tmp_path / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True, exist_ok=True)
    canonical_health_payload = {
        "schema": "SessionHealth", "schema_version": "1.0.0",
        "run_id": "state-run", "status": "ok", "updated_at": "2026-03-08T00:00:00+00:00",
        "contamination_risk": "low", "overthinking_score": 0.1,
        "context_health": "green", "verification_status": "ok",
        "recommended_action": "continue",
    }
    latest_health_payload = {
        "schema": "SessionHealth", "schema_version": "1.0.0",
        "run_id": "legacy-run", "status": "ok", "updated_at": "2026-03-07T00:00:00+00:00",
        "contamination_risk": "high", "overthinking_score": 0.8,
        "context_health": "red", "verification_status": "blocked",
        "recommended_action": "block",
    }
    (health_dir / "state-run.json").write_text(json.dumps(canonical_health_payload), encoding="utf-8")
    (health_dir / "latest.json").write_text(json.dumps(latest_health_payload), encoding="utf-8")

    result = dispatch_specialists(_valid_job(), str(tmp_path))

    assert result["status"] == "ok"
    evidence_path = Path(str(result["evidence_path"]))
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert "defense_state" in payload
    assert "session_health" in payload
    assert payload["defense_state"]["controls"]["firewall"] == "canonical"
    assert payload["session_health"]["run_id"] == "state-run"


def test_dispatch_evidence_falls_back_to_latest_when_run_scoped_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_RUN_ID", "missing-run")

    defense_dir = tmp_path / ".omg" / "state" / "defense_state"
    defense_dir.mkdir(parents=True, exist_ok=True)
    (defense_dir / "latest.json").write_text(
        json.dumps({"schema": "DefenseState", "run_id": "legacy-run", "controls": {"firewall": "legacy"}}),
        encoding="utf-8",
    )

    health_dir = tmp_path / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True, exist_ok=True)
    (health_dir / "latest.json").write_text(
        json.dumps({"schema": "SessionHealth", "run_id": "legacy-run", "recommended_action": "continue"}),
        encoding="utf-8",
    )

    result = dispatch_specialists(_valid_job(), str(tmp_path))

    assert result["status"] == "ok"
    evidence_path = Path(str(result["evidence_path"]))
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["defense_state"]["controls"]["firewall"] == "legacy"
    assert payload["session_health"]["run_id"] == "legacy-run"


def test_dispatch_evidence_uses_explicit_run_id_for_state_lookup(tmp_path: Path) -> None:
    defense_dir = tmp_path / ".omg" / "state" / "defense_state"
    defense_dir.mkdir(parents=True, exist_ok=True)
    (defense_dir / "forge-run-42.json").write_text(
        json.dumps({"schema": "DefenseState", "run_id": "forge-run-42", "controls": {"firewall": "run-scoped"}}),
        encoding="utf-8",
    )

    health_dir = tmp_path / ".omg" / "state" / "session_health"
    health_dir.mkdir(parents=True, exist_ok=True)
    (health_dir / "forge-run-42.json").write_text(
        json.dumps({"schema": "SessionHealth", "run_id": "forge-run-42", "recommended_action": "continue"}),
        encoding="utf-8",
    )

    result = dispatch_specialists(_valid_job(), str(tmp_path), run_id="forge-run-42")

    evidence_path = Path(str(result["evidence_path"]))
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["defense_state"]["controls"]["firewall"] == "run-scoped"
    assert payload["session_health"]["run_id"] == "forge-run-42"


def test_resolve_adapters_returns_axolotl_and_pybullet_for_vision_job() -> None:
    job: dict[str, object] = {
        "specialists": ["data-curator", "training-architect", "simulator-engineer"],
        "domain": "vision",
    }
    adapters = resolve_adapters(job)
    adapter_names = [str(a["adapter"]) for a in adapters]
    assert "axolotl" in adapter_names
    assert "pybullet" in adapter_names
    for a in adapters:
        assert a["status"] in ("invoked", "skipped_unavailable_backend")
        assert "kind" in a
        assert "available" in a


def test_resolve_adapters_skips_axolotl_when_no_training_architect() -> None:
    job: dict[str, object] = {
        "specialists": ["simulator-engineer"],
        "domain": "robotics",
    }
    adapters = resolve_adapters(job)
    adapter_names = [str(a["adapter"]) for a in adapters]
    assert "axolotl" not in adapter_names
    assert "pybullet" in adapter_names


def test_resolve_adapters_uses_requested_simulator_backend() -> None:
    job: dict[str, object] = {
        "specialists": ["simulator-engineer"],
        "simulator_backend": "gazebo",
    }
    adapters = resolve_adapters(job)
    adapter_names = [str(a["adapter"]) for a in adapters]
    assert "gazebo" in adapter_names
    assert "pybullet" not in adapter_names


def test_resolve_adapters_falls_back_to_pybullet_for_unknown_backend() -> None:
    job: dict[str, object] = {
        "specialists": ["simulator-engineer"],
        "simulator_backend": "nonexistent",
    }
    adapters = resolve_adapters(job)
    adapter_names = [str(a["adapter"]) for a in adapters]
    assert "pybullet" in adapter_names


def test_check_backend_available_returns_false_for_missing_module() -> None:
    assert _check_backend_available("axolotl") is False
    assert _check_backend_available("gazebo") is False
    assert _check_backend_available("isaac_gym") is False


def test_check_backend_available_returns_false_for_unknown_name() -> None:
    assert _check_backend_available("totally_unknown") is False


def test_check_required_backends_satisfied_passes_for_optional() -> None:
    evidence: list[dict[str, object]] = [
        {"adapter": "pybullet", "status": "skipped_unavailable_backend", "required": False},
    ]
    ok, reason = check_required_backends_satisfied(evidence)
    assert ok is True
    assert reason == "ok"


def test_check_required_backends_satisfied_fails_for_required() -> None:
    evidence: list[dict[str, object]] = [
        {"adapter": "gazebo", "status": "skipped_unavailable_backend", "required": True},
    ]
    ok, reason = check_required_backends_satisfied(evidence)
    assert ok is False
    assert "gazebo" in reason


def test_dispatch_specialists_includes_adapter_evidence(tmp_path: Path) -> None:
    result = dispatch_specialists(_valid_job(), str(tmp_path))
    assert result["status"] == "ok"
    assert "adapter_evidence" in result
    adapter_evidence = result["adapter_evidence"]
    assert isinstance(adapter_evidence, list)
    assert len(adapter_evidence) >= 2
    adapter_names = [str(a["adapter"]) for a in adapter_evidence]
    assert "axolotl" in adapter_names
    assert "pybullet" in adapter_names


def test_dispatch_specialists_blocks_when_required_backend_unavailable(tmp_path: Path) -> None:
    job = _valid_job()
    job["simulator_backend"] = "gazebo"
    job["require_backend"] = True

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert "required backend unavailable" in str(result.get("reason", ""))
    assert "adapter_evidence" in result


def test_dispatch_specialists_continues_when_optional_backend_unavailable(tmp_path: Path) -> None:
    job = _valid_job()
    job["simulator_backend"] = "gazebo"
    job["require_backend"] = False

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "ok"
    assert "adapter_evidence" in result
    adapter_evidence = result["adapter_evidence"]
    gazebo_ev = [a for a in adapter_evidence if a["adapter"] == "gazebo"]
    assert len(gazebo_ev) == 1
    assert gazebo_ev[0]["status"] == "skipped_unavailable_backend"
    assert gazebo_ev[0]["required"] is False


def test_forge_vision_agent_labs_only_enforcement() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "omg.py"),
            "forge",
            "vision-agent",
            "--preset",
            "safe",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    output = json.loads(result.stdout)
    assert output["status"] == "error"
    assert "labs" in output["message"]


# --- Task 12: Forge cybersecurity proof-backed evidence tests ---

from unittest.mock import patch


def _cybersecurity_job() -> dict[str, object]:
    return {
        "dataset": {
            "name": "cybersecurity",
            "license": "apache-2.0",
            "source": "internal-curated",
        },
        "base_model": {
            "name": "distill-base-v1",
            "source": "approved-registry",
            "allow_distill": True,
        },
        "target_metric": 0.8,
        "domain": "cybersecurity",
        "specialists": ["forge-cybersecurity"],
    }


def test_dispatch_cybersecurity_runs_security_scan(tmp_path: Path) -> None:
    """Cybersecurity specialist must run security_check and include scan results."""
    result = dispatch_specialists(_cybersecurity_job(), str(tmp_path))

    assert result["status"] == "ok"
    assert result["specialists_dispatched"] == ["forge-cybersecurity"]
    assert "security_scan" in result

    scan = result["security_scan"]
    assert scan["schema"] == "SecurityCheckResult"
    assert "findings" in scan
    assert "security_scans" in scan
    assert isinstance(scan["security_scans"], list)
    assert "evidence" in scan
    evidence_block = scan["evidence"]
    assert "sarif_path" in evidence_block
    assert "sbom_path" in evidence_block

    # Evidence file must also persist security scan data
    evidence_path = Path(str(result["evidence_path"]))
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert "security_scan" in payload
    assert payload["security_scan"]["schema"] == "SecurityCheckResult"


def test_dispatch_cybersecurity_degrades_gracefully_without_semgrep(tmp_path: Path) -> None:
    """Semgrep missing must not crash — still produces structured result."""
    with patch("runtime.security_check.shutil.which", return_value=None):
        result = dispatch_specialists(_cybersecurity_job(), str(tmp_path))

    assert result["status"] == "ok"
    assert "security_scan" in result
    scan = result["security_scan"]
    assert scan["schema"] == "SecurityCheckResult"
    assert scan["status"] in ("ok", "error")
    assert "findings" in scan
    assert isinstance(scan["findings"], list)


def test_dispatch_cybersecurity_evidence_compatible_with_proof_gate(tmp_path: Path) -> None:
    """Forge cybersecurity evidence must include fields proof-gate consumers expect."""
    result = dispatch_specialists(_cybersecurity_job(), str(tmp_path))
    scan = result["security_scan"]

    # proof-gate expects security_scans list with tool+findings
    assert "security_scans" in scan
    for entry in scan["security_scans"]:
        assert "tool" in entry
        assert "findings" in entry

    # proof-gate expects unresolved_risks list
    assert "unresolved_risks" in scan
    assert isinstance(scan["unresolved_risks"], list)

    # proof-gate expects evidence block with sarif_path
    assert "evidence" in scan
    assert "sarif_path" in scan["evidence"]


def test_dispatch_non_cybersecurity_has_no_security_scan(tmp_path: Path) -> None:
    """Non-cybersecurity dispatches must NOT include security_scan."""
    result = dispatch_specialists(_valid_job(), str(tmp_path))
    assert result["status"] == "ok"
    assert "security_scan" not in result
