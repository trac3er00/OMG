from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from runtime.forge_agents import dispatch_specialists, get_specialist_registry, resolve_specialists

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
    assert "description" in registry["data-curator"]
    assert "capabilities" in registry["simulator-engineer"]


def test_dispatch_specialists_writes_evidence_and_returns_shape(tmp_path: Path) -> None:
    result = dispatch_specialists(_valid_job(), str(tmp_path))

    assert result["status"] == "ok"
    assert result["specialists_dispatched"] == [
        "data-curator",
        "training-architect",
        "simulator-engineer",
    ]
    evidence_path = Path(str(result["evidence_path"]))
    assert evidence_path.exists()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "ForgeSpecialistDispatchEvidence"
    assert payload["contract"]["labs_only"] is True


def test_dispatch_specialists_blocks_when_contract_mismatch(tmp_path: Path) -> None:
    job = _valid_job()
    job["specialists"] = ["data-curator"]

    result = dispatch_specialists(job, str(tmp_path))

    assert result["status"] == "blocked"
    assert "missing required specialists" in str(result["reason"])
    assert result["evidence_path"] == ""


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
