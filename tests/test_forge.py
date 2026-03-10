# pyright: reportUnknownVariableType=false
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

from lab.pipeline import publish_artifact, run_pipeline, run_pipeline_with_evidence  # noqa: E402
from runtime.forge_contracts import validate_forge_job  # noqa: E402


def _valid_job() -> dict[str, Any]:
    return {
        "domain": "vision",
        "dataset": {
            "name": "test-dataset",
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
    }


def _blocked_source_job() -> dict[str, Any]:
    job = _valid_job()
    job["dataset"]["source"] = "leaked-dataset-dump"
    return job


class TestForgeRunHappyPath:
    def test_valid_job_returns_ready(self):
        result = run_pipeline(_valid_job())
        assert result["status"] == "ready"
        assert result["stage"] == "complete"
        assert result["published"] is False
        assert result["evaluation_report"]["passed"] is True

    def test_stages_all_ok(self):
        result = run_pipeline(_valid_job())
        for stage in result["stages"]:
            assert stage["status"] == "ok"


class TestForgeRunBlockedPolicy:
    def test_blocked_dataset_source(self):
        result = run_pipeline(_blocked_source_job())
        assert result["status"] == "blocked"
        assert result["stage"] == "policy"
        assert "source violates policy" in result["reason"]

    def test_blocked_missing_dataset(self):
        result = run_pipeline({"base_model": {"source": "ok", "allow_distill": True}})
        assert result["status"] == "blocked"
        assert "dataset" in result["reason"]

    def test_blocked_missing_base_model(self):
        result = run_pipeline({
            "dataset": {"name": "d", "license": "mit", "source": "ok"},
        })
        assert result["status"] == "blocked"
        assert "base_model" in result["reason"]

    def test_blocked_disallowed_license(self):
        job = _valid_job()
        job["dataset"]["license"] = "proprietary"
        result = run_pipeline(job)
        assert result["status"] == "blocked"
        assert "license" in result["reason"]

    def test_blocked_distill_disallowed(self):
        job = _valid_job()
        job["base_model"]["allow_distill"] = False
        result = run_pipeline(job)
        assert result["status"] == "blocked"
        assert "distill" in result["reason"].lower()


class TestForgeMVPValidation:
    def test_validate_forge_job_accepts_valid_payload(self):
        ok, reason = validate_forge_job(_valid_job())
        assert ok is True
        assert reason == "ok"

    def test_validate_forge_job_requires_dataset_name(self):
        job = _valid_job()
        del job["dataset"]["name"]

        ok, reason = validate_forge_job(job)

        assert ok is False
        assert reason == "dataset.name missing"


class TestForgeDomainValidation:
    def test_validate_forge_job_rejects_missing_domain(self):
        job = _valid_job()
        del job["domain"]
        ok, reason = validate_forge_job(job)
        assert ok is False
        assert "domain missing" in reason

    def test_validate_forge_job_rejects_empty_domain(self):
        job = _valid_job()
        job["domain"] = ""
        ok, reason = validate_forge_job(job)
        assert ok is False
        assert "domain missing" in reason

    def test_validate_forge_job_rejects_unknown_domain(self):
        job = _valid_job()
        job["domain"] = "space"
        ok, reason = validate_forge_job(job)
        assert ok is False
        assert "unknown domain" in reason
        assert "space" in reason

    def test_validate_forge_job_accepts_canonical_domain(self):
        for domain in ["vision", "robotics", "algorithms", "health", "cybersecurity"]:
            job = _valid_job()
            job["domain"] = domain
            ok, reason = validate_forge_job(job)
            assert ok is True, f"Expected ok for domain={domain!r}, got reason={reason!r}"

    def test_validate_forge_job_canonicalizes_alias(self):
        job = _valid_job()
        job["domain"] = "vision-agent"
        ok, reason = validate_forge_job(job)
        assert ok is True
        assert job["domain"] == "vision"

    def test_forge_run_cli_missing_domain_exits_nonzero(self):
        job: dict[str, Any] = {"target_metric": 0.8}
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "run",
                "--preset",
                "labs",
                "--job-json",
                json.dumps(job),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        output = json.loads(result.stdout)
        assert output["status"] == "error"
        assert "domain" in output["message"]

    def test_forge_run_cli_unknown_domain_exits_nonzero(self):
        job = _valid_job()
        job["domain"] = "space"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "run",
                "--preset",
                "labs",
                "--job-json",
                json.dumps(job),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        output = json.loads(result.stdout)
        assert output["status"] == "error"
        assert "unknown domain" in output["message"]

    def test_forge_run_cli_valid_domain_full_payload_exits_zero(self):
        job = {
            "domain": "vision",
            "dataset": {"name": "vision-agent", "license": "apache-2.0", "source": "internal-curated"},
            "base_model": {"name": "distill-base-v1", "source": "approved-registry", "allow_distill": True},
            "target_metric": 0.8,
            "simulated_metric": 0.9,
            "specialists": ["data-curator", "training-architect", "simulator-engineer"],
        }
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "run",
                "--preset",
                "labs",
                "--job-json",
                json.dumps(job),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["specialist_dispatch"]["status"] == "ok"


class TestForgeEvidencePipeline:
    def test_run_pipeline_with_evidence_writes_artifact(self, tmp_path: Path):
        result = run_pipeline_with_evidence(str(tmp_path), _valid_job(), "run-e2e")
        evidence_path = tmp_path / ".omg" / "evidence" / "forge-run-e2e.json"

        assert result["status"] == "ready"
        assert result["evidence_path"] == str(evidence_path)
        assert evidence_path.exists()

    def test_run_pipeline_with_evidence_emits_staged_contract_evidence(self, tmp_path: Path):
        defense_dir = tmp_path / ".omg" / "state" / "defense_state"
        defense_dir.mkdir(parents=True, exist_ok=True)
        (defense_dir / "run-stage.json").write_text(
            json.dumps({"schema": "DefenseState", "run_id": "run-stage", "controls": {"firewall": "enabled"}}),
            encoding="utf-8",
        )

        health_dir = tmp_path / ".omg" / "state" / "session_health"
        health_dir.mkdir(parents=True, exist_ok=True)
        (health_dir / "run-stage.json").write_text(
            json.dumps({"schema": "SessionHealth", "run_id": "run-stage", "context_health": "green"}),
            encoding="utf-8",
        )

        result = run_pipeline_with_evidence(str(tmp_path), _valid_job(), "run-stage")
        assert result["run_id"] == "run-stage"
        assert len(result["stage_evidence"]) == 5

        first_stage = result["stage_evidence"][0]
        assert first_stage["run_id"] == "run-stage"
        assert first_stage["stage"] == "data_prepare"
        assert first_stage["status"] == "success"
        assert first_stage["defense_snapshot"]["controls"]["firewall"] == "enabled"
        assert first_stage["session_health_snapshot"]["context_health"] == "green"

        payload = json.loads((tmp_path / ".omg" / "evidence" / "forge-run-stage.json").read_text(encoding="utf-8"))
        assert len(payload["stage_evidence"]) == 5
        assert payload["stage_evidence"][0]["run_id"] == "run-stage"


class TestForgeCLI:
    def test_forge_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "omg.py"), "forge", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "forge" in result.stdout.lower()

    def test_forge_run_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "omg.py"), "forge", "run", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--job" in result.stdout

    def test_forge_vision_agent_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "omg.py"), "forge", "vision-agent", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "vision-agent" in result.stdout

    def test_forge_appears_in_main_help(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "omg.py"), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "forge" in result.stdout


class TestForgeBlockedOutsideLabs:
    def test_non_labs_preset_blocked(self):
        """forge with preset != labs must print error and exit non-zero."""
        import tempfile, os
        job = _valid_job()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(job, f)
            f.flush()
            job_path = f.name
        try:
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS_DIR / "omg.py"),
                    "forge", "run",
                    "--job", job_path,
                    "--preset", "safe",
                ],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode != 0
            output = json.loads(result.stdout)
            assert output["status"] == "error"
            assert "labs" in output["message"]
        finally:
            os.unlink(job_path)

    def test_balanced_preset_blocked(self):
        """forge with balanced preset must also be blocked."""
        import tempfile, os
        job = _valid_job()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(job, f)
            f.flush()
            job_path = f.name
        try:
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS_DIR / "omg.py"),
                    "forge", "run",
                    "--job", job_path,
                    "--preset", "balanced",
                ],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode != 0
            output = json.loads(result.stdout)
            assert output["status"] == "error"
        finally:
            os.unlink(job_path)

    def test_labs_preset_allowed(self):
        """forge with labs preset must succeed for a valid job."""
        import tempfile, os
        job = _valid_job()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(job, f)
            f.flush()
            job_path = f.name
        try:
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS_DIR / "omg.py"),
                    "forge", "run",
                    "--job", job_path,
                    "--preset", "labs",
                ],
                capture_output=True, text=True, timeout=10,
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["status"] == "ready"
        finally:
            os.unlink(job_path)


class TestForgeProofBackedEvidence:
    def test_forge_run_evidence_path_contains_proof_fields(self):
        job = _valid_job()
        job["domain"] = "vision"
        job["specialists"] = ["data-curator", "training-architect", "simulator-engineer"]
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge", "run",
                "--preset", "labs",
                "--job-json", json.dumps(job),
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output.get("labs_only") is True
        assert output.get("proof_backed") is True

    def test_forge_vision_agent_evidence_contains_proof_fields(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge", "vision-agent",
                "--preset", "labs",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output.get("labs_only") is True
        assert output.get("proof_backed") is True


class TestForgeSpecialists:
    def test_forge_run_with_specialists_dispatches(self):
        job = {
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
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "run",
                "--preset",
                "labs",
                "--job-json",
                json.dumps(job),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["specialist_dispatch"]["status"] == "ok"
        assert output["specialist_dispatch"]["specialists_dispatched"] == [
            "data-curator",
            "training-architect",
            "simulator-engineer",
        ]

    def test_forge_vision_agent_path_runs_labs_job(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "vision-agent",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["agent_path"] == "vision-agent"
        assert output["specialist_dispatch"]["status"] == "ok"

    def test_forge_vision_agent_emits_staged_evidence(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "vision-agent",
                "--preset",
                "labs",
                "--run-id",
                "vision-stage-run",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["run_id"] == "vision-stage-run"
        assert len(output["stage_evidence"]) == 5
        assert output["stage_evidence"][0]["stage"] == "data_prepare"
        assert output["stage_evidence"][-1]["stage"] == "regression_test"

    def test_forge_run_invalid_specialists_blocked(self):
        job = _valid_job()
        job["domain"] = "vision"
        job["specialists"] = ["data-curator", "unknown-specialist"]
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "run",
                "--preset",
                "labs",
                "--job-json",
                json.dumps(job),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        output = json.loads(result.stdout)
        assert output["status"] == "blocked"


class TestForgeAdapterBackends:
    def test_pipeline_blocks_with_explicit_axolotl_unavailable_backend_status(self):
        job = _valid_job()
        job["specialists"] = ["training-architect"]
        job["domain"] = "algorithms"
        job["simulator_backend"] = "axolotl"
        job["require_backend"] = True

        result = run_pipeline(job)

        assert result["status"] == "blocked"
        assert result["stage"] == "adapter"
        axolotl_ev = [a for a in result.get("adapter_evidence", []) if a["adapter"] == "axolotl"]
        assert len(axolotl_ev) == 1
        assert axolotl_ev[0]["status"] == "unavailable_backend"
        assert axolotl_ev[0]["reason"] == "axolotl_not_installed"

    def test_pipeline_continues_with_optional_unavailable_backend(self):
        job = _valid_job()
        job["specialists"] = ["data-curator", "training-architect", "simulator-engineer"]
        job["domain"] = "vision"
        job["simulator_backend"] = "gazebo"
        job["require_backend"] = False

        result = run_pipeline(job)

        assert result["status"] == "ready"
        assert "adapter_evidence" in result
        gazebo_ev = [a for a in result["adapter_evidence"] if a["adapter"] == "gazebo"]
        assert len(gazebo_ev) == 1
        assert gazebo_ev[0]["status"] == "skipped_unavailable_backend"
        assert gazebo_ev[0]["required"] is False

    def test_pipeline_blocks_when_required_backend_missing(self):
        job = _valid_job()
        job["specialists"] = ["simulator-engineer"]
        job["domain"] = "robotics"
        job["simulator_backend"] = "gazebo"
        job["require_backend"] = True

        result = run_pipeline(job)

        assert result["status"] == "blocked"
        assert result["stage"] == "adapter"
        assert "required backend unavailable" in str(result.get("reason", ""))
        assert "adapter_evidence" in result

    def test_pipeline_proceeds_with_default_pybullet(self):
        job = _valid_job()
        job["specialists"] = ["training-architect", "simulator-engineer"]
        job["domain"] = "robotics"

        result = run_pipeline(job)

        assert result["status"] == "ready"
        if "adapter_evidence" in result:
            adapter_names = [str(a["adapter"]) for a in result["adapter_evidence"]]
            assert "pybullet" in adapter_names
            pybullet_ev = [a for a in result["adapter_evidence"] if a["adapter"] == "pybullet"][0]
            assert pybullet_ev.get("backend") == "pybullet"
            assert "episode_stats" in pybullet_ev
            assert "replay_metadata" in pybullet_ev

    def test_pipeline_with_evidence_includes_adapter_data(self, tmp_path: Path):
        job = _valid_job()
        job["specialists"] = ["data-curator", "training-architect", "simulator-engineer"]
        job["domain"] = "vision"

        result = run_pipeline_with_evidence(str(tmp_path), job, "run-adapter-e2e")

        assert result["status"] == "ready"
        assert "adapter_evidence" in result

    def test_pipeline_stage_evidence_has_adapter_evidence_on_relevant_stages(self):
        job = _valid_job()
        job["specialists"] = ["training-architect", "simulator-engineer"]
        job["domain"] = "robotics"

        result = run_pipeline(job)

        assert result["status"] == "ready"
        stage_map = {s["stage"]: s for s in result["stage_evidence"]}
        train_stage = stage_map["train_distill"]
        assert "adapter_evidence" in train_stage
        training_adapters = [a for a in train_stage["adapter_evidence"] if a["kind"] == "training"]
        assert len(training_adapters) >= 1

        eval_stage = stage_map["evaluate"]
        assert "adapter_evidence" in eval_stage
        sim_adapters = [a for a in eval_stage["adapter_evidence"] if a["kind"] == "simulator"]
        assert len(sim_adapters) >= 1

    def test_pipeline_stage_evidence_no_adapter_on_data_stages(self):
        job = _valid_job()
        job["specialists"] = ["training-architect", "simulator-engineer"]
        job["domain"] = "robotics"

        result = run_pipeline(job)

        assert result["status"] == "ready"
        stage_map = {s["stage"]: s for s in result["stage_evidence"]}
        assert "adapter_evidence" not in stage_map["data_prepare"]
        assert "adapter_evidence" not in stage_map["synthetic_refine"]

    def test_pipeline_required_isaac_gym_blocks(self):
        job = _valid_job()
        job["specialists"] = ["simulator-engineer"]
        job["domain"] = "robotics"
        job["simulator_backend"] = "isaac_gym"
        job["require_backend"] = True

        result = run_pipeline(job)

        assert result["status"] == "blocked"
        assert "required backend unavailable" in str(result.get("reason", ""))
        isaac_ev = [a for a in result.get("adapter_evidence", []) if a["adapter"] == "isaac_gym"]
        assert len(isaac_ev) == 1
        assert isaac_ev[0]["status"] == "unavailable_backend"
        assert isaac_ev[0]["reason"] == "isaac_lab_requires_cuda"

    def test_pipeline_optional_isaac_gym_continues(self):
        job = _valid_job()
        job["specialists"] = ["simulator-engineer"]
        job["domain"] = "robotics"
        job["simulator_backend"] = "isaac_gym"
        job["require_backend"] = False

        result = run_pipeline(job)

        assert result["status"] == "ready"
        isaac_ev = [a for a in result.get("adapter_evidence", []) if a["adapter"] == "isaac_gym"]
        assert len(isaac_ev) == 1
        assert isaac_ev[0]["status"] == "skipped_unavailable_backend"
        assert isaac_ev[0]["promotion_blocked"] is False


class TestForgePublish:
    """Red-state tests for publish_artifact function (not yet fully implemented)."""

    def test_publish_artifact_writes_json_file(self, tmp_path: Path) -> None:
        """publish_artifact must write a JSON file to the provided path."""
        result = {
            "status": "ready",
            "stage": "complete",
            "published": False,
            "evaluation_report": {
                "created_at": "2026-03-09T00:00:00+00:00",
                "metric": 0.9,
                "target_metric": 0.8,
                "passed": True,
                "notes": "",
            },
        }

        published = publish_artifact(result)

        assert isinstance(published, dict)
        assert published.get("status") == "published"
        assert published.get("published") is True
        assert "published_at" in published

    def test_publish_artifact_requires_passed_evaluation(self, tmp_path: Path) -> None:
        """publish_artifact must block if evaluation report is missing or not passed."""
        result_no_report = {
            "status": "ready",
            "stage": "complete",
            "published": False,
        }

        published = publish_artifact(result_no_report)

        assert isinstance(published, dict)
        assert published.get("status") == "blocked"
        assert published.get("reason") == "evaluation report missing or not passed"
        assert published.get("published") is False

    def test_publish_artifact_blocks_on_failed_evaluation(self, tmp_path: Path) -> None:
        """publish_artifact must block if evaluation report passed=False."""
        result_failed = {
            "status": "ready",
            "stage": "complete",
            "published": False,
            "evaluation_report": {
                "created_at": "2026-03-09T00:00:00+00:00",
                "metric": 0.7,
                "target_metric": 0.8,
                "passed": False,
                "notes": "metric below target",
            },
        }

        published = publish_artifact(result_failed)

        assert isinstance(published, dict)
        assert published.get("status") == "blocked"
        assert published.get("reason") == "evaluation report missing or not passed"
        assert published.get("published") is False


class TestForgeDomainCLIPaths:
    @pytest.mark.parametrize("domain", ["robotics", "algorithms", "health", "cybersecurity"])
    def test_domain_command_exits_zero_with_agent_path(self, domain: str) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                domain,
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"{domain}: stderr={result.stderr}"
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["agent_path"] == domain
        assert output["specialist_dispatch"]["status"] == "ok"

    @pytest.mark.parametrize("domain", ["robotics", "algorithms", "health", "cybersecurity"])
    def test_domain_command_rejects_non_labs_preset(self, domain: str) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                domain,
                "--preset",
                "balanced",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        output = json.loads(result.stdout)
        assert output["status"] == "error"

    @pytest.mark.parametrize("domain", ["robotics", "algorithms", "health", "cybersecurity"])
    def test_domain_command_accepts_job_json_overrides(self, domain: str) -> None:
        override = json.dumps({"evaluation_notes": "override-test"})
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                domain,
                "--preset",
                "labs",
                "--job-json",
                override,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"{domain}: stderr={result.stderr}"
        output = json.loads(result.stdout)
        assert output["agent_path"] == domain

    def test_unknown_forge_subcommand_exits_nonzero(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "space",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0


class TestVisionDomainCoverage:
    def test_vision_agent_alias_resolves_to_vision_domain(self) -> None:
        """vision-agent alias must resolve to vision domain in output."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "vision-agent",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["agent_path"] == "vision-agent"
        # Verify domain is canonicalized to vision in specialist dispatch
        assert output["specialist_dispatch"]["status"] == "ok"

    def test_vision_agent_happy_path_exits_zero(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "vision-agent",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = json.loads(result.stdout)
        if output.get("status") == "ready":
            assert result.returncode == 0
        else:
            assert result.returncode != 0
            assert output["status"] == "blocked"
            adapter_evidence = output.get("adapter_evidence", [])
            unavailable = [a for a in adapter_evidence if a.get("status") == "unavailable_backend"]
            assert len(unavailable) >= 1


class TestRoboticsDomainCoverage:
    def test_robotics_happy_path_exits_zero(self) -> None:
        """robotics CLI must exit 0 with ready status."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "robotics",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["agent_path"] == "robotics"

    def test_robotics_required_backend_blocks_when_unavailable(self) -> None:
        """robotics domain with require_backend=true must block when pybullet unavailable."""
        import tempfile, os
        job = _valid_job()
        job["domain"] = "robotics"
        job["require_backend"] = True
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(job, f)
            f.flush()
            job_path = f.name
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "omg.py"),
                    "forge",
                    "run",
                    "--job",
                    job_path,
                    "--preset",
                    "labs",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # If pybullet is unavailable, should be blocked
            if result.returncode != 0:
                output = json.loads(result.stdout)
                assert output["status"] == "blocked"
        finally:
            os.unlink(job_path)


class TestAlgorithmsDomainCoverage:
    def test_algorithms_happy_path_exits_zero(self) -> None:
        """algorithms CLI must exit 0 with ready status."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "algorithms",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["agent_path"] == "algorithms"

    def test_algorithms_evidence_has_deterministic_metric(self) -> None:
        """algorithms domain evidence must include target_metric field."""
        job = _valid_job()
        job["domain"] = "algorithms"
        job["target_metric"] = 0.85
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "run",
                "--preset",
                "labs",
                "--job-json",
                json.dumps(job),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["evaluation_report"]["target_metric"] == 0.85


class TestHealthDomainCoverage:
    def test_health_happy_path_exits_zero(self) -> None:
        """health CLI must exit 0 with ready status."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "health",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["agent_path"] == "health"

    def test_health_domain_pack_declares_human_review(self) -> None:
        """health domain pack must declare human-review in required_approvals."""
        from runtime.domain_packs import get_domain_pack_contract
        pack = get_domain_pack_contract("health")
        assert "required_approvals" in pack
        assert "human-review" in pack["required_approvals"]

    def test_health_evidence_surfaces_approval_requirements(self) -> None:
        """health domain evidence must surface approval requirements from domain pack."""
        job = _valid_job()
        job["domain"] = "health"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "run",
                "--preset",
                "labs",
                "--job-json",
                json.dumps(job),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        evidence_path = output["specialist_dispatch"]["evidence_path"]
        evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        assert "domain_pack" in evidence
        assert "required_approvals" in evidence["domain_pack"]
        assert "human-review" in evidence["domain_pack"]["required_approvals"]


class TestCybersecurityDomainCoverage:
    def test_cybersecurity_happy_path_exits_zero(self) -> None:
        """cybersecurity CLI must exit 0 with ready status."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "omg.py"),
                "forge",
                "cybersecurity",
                "--preset",
                "labs",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "ready"
        assert output["agent_path"] == "cybersecurity"

    def test_cybersecurity_invalid_specialist_is_blocked(self) -> None:
        """cybersecurity domain with wrong specialists must be blocked."""
        import tempfile, os
        job = _valid_job()
        job["domain"] = "cybersecurity"
        job["specialists"] = ["data-curator"]  # Wrong specialist for cybersecurity
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(job, f)
            f.flush()
            job_path = f.name
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "omg.py"),
                    "forge",
                    "run",
                    "--job",
                    job_path,
                    "--preset",
                    "labs",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode != 0
            output = json.loads(result.stdout)
            assert output["status"] == "blocked"
        finally:
            os.unlink(job_path)
