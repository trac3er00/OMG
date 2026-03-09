"""Tests for full lab pipeline policy gating and publish rules."""

from lab.pipeline import run_pipeline, publish_artifact


def test_pipeline_blocks_invalid_dataset_license():
    result = run_pipeline(
        {
            "dataset": {"source": "internal-clean", "license": "proprietary"},
            "base_model": {"source": "open-model", "allow_distill": True},
            "target_metric": 0.8,
            "simulated_metric": 0.9,
        }
    )
    assert result["status"] == "blocked"
    assert result["stage"] == "policy"


def test_pipeline_fails_without_eval_threshold():
    result = run_pipeline(
        {
            "dataset": {"source": "clean-source", "license": "mit"},
            "base_model": {"source": "open-model", "allow_distill": True},
            "target_metric": 0.9,
            "simulated_metric": 0.8,
        }
    )
    assert result["status"] == "failed_evaluation"
    pub = publish_artifact(result)
    assert pub["status"] == "blocked"


def test_pipeline_ready_then_publish_with_report():
    result = run_pipeline(
        {
            "dataset": {"source": "clean-source", "license": "apache-2.0"},
            "base_model": {"source": "open-model", "allow_distill": True},
            "target_metric": 0.75,
            "simulated_metric": 0.9,
        }
    )
    assert result["status"] == "ready"
    assert result["evaluation_report"]["passed"] is True
    pub = publish_artifact(result)
    assert pub["status"] == "published"
    assert pub["published"] is True


def test_pipeline_exits_cleanly_on_stage_timeout() -> None:
    result = run_pipeline(
        {
            "dataset": {"source": "clean-source", "license": "apache-2.0"},
            "base_model": {"source": "open-model", "allow_distill": True},
            "target_metric": 0.75,
            "simulated_metric": 0.9,
            "stage_timeouts_ms": {"synthetic_refine": 1},
            "stage_durations_ms": {"synthetic_refine": 10},
        },
        run_id="timeout-run",
        project_dir=".",
    )

    assert result["status"] == "stage_timeout"
    assert result["stage"] == "synthetic_refine"
    assert result["published"] is False
    assert result["stage_evidence"][-1]["status"] == "timeout"


def test_pipeline_exits_cleanly_on_failed_stage() -> None:
    result = run_pipeline(
        {
            "dataset": {"source": "clean-source", "license": "apache-2.0"},
            "base_model": {"source": "open-model", "allow_distill": True},
            "target_metric": 0.75,
            "simulated_metric": 0.9,
            "fail_stage": "train_distill",
        },
        run_id="failed-run",
        project_dir=".",
    )

    assert result["status"] == "failed_stage"
    assert result["stage"] == "train_distill"
    assert result["published"] is False
    assert result["stage_evidence"][-1]["status"] == "failed"
