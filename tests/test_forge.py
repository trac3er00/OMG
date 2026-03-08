# pyright: reportUnknownVariableType=false
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

from lab.pipeline import run_pipeline, run_pipeline_with_evidence  # noqa: E402
from runtime.forge_contracts import validate_forge_job  # noqa: E402


def _valid_job() -> dict[str, Any]:
    return {
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


class TestForgeEvidencePipeline:
    def test_run_pipeline_with_evidence_writes_artifact(self, tmp_path: Path):
        result = run_pipeline_with_evidence(str(tmp_path), _valid_job(), "run-e2e")
        evidence_path = tmp_path / ".omg" / "evidence" / "forge-run-e2e.json"

        assert result["status"] == "ready"
        assert result["evidence_path"] == str(evidence_path)
        assert evidence_path.exists()


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
