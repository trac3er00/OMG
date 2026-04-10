from __future__ import annotations

import json
import os

import pytest

from runtime.eval_gate import EvalSnapshot, RegressionDetector


@pytest.fixture()
def history_dir(tmp_path):
    return str(tmp_path / "eval-history")


@pytest.fixture()
def detector(history_dir):
    return RegressionDetector(history_dir=history_dir)


def _snap(
    metrics: dict[str, float],
    snapshot_id: str = "snap-1",
    session_id: str | None = None,
) -> EvalSnapshot:
    return EvalSnapshot(
        snapshot_id=snapshot_id,
        timestamp="2026-04-10T00:00:00Z",
        metrics=metrics,
        session_id=session_id,
    )


class TestRegressionBlock:
    def test_regression_block(self, detector):
        baseline = _snap({"accuracy": 0.90, "latency": 0.80}, snapshot_id="base")
        current = _snap({"accuracy": 0.60, "latency": 0.80}, snapshot_id="cur")

        result = detector.check_release_gate(current, baseline)

        assert result["passed"] is False
        assert len(result["regressions"]) == 1
        reg = result["regressions"][0]
        assert reg["metric"] == "accuracy"
        assert reg["baseline"] == 0.90
        assert reg["current"] == 0.60
        assert reg["regression_pct"] == pytest.approx(1 / 3, abs=1e-6)
        assert "1 metric(s) regressed" in result["message"]


class TestNoRegression:
    def test_no_regression(self, detector):
        baseline = _snap({"accuracy": 0.90, "latency": 0.80})
        current = _snap({"accuracy": 0.90, "latency": 0.85})

        result = detector.check_release_gate(current, baseline)

        assert result["passed"] is True
        assert result["regressions"] == []
        assert result["message"] == "All eval metrics within threshold"


class TestSmallRegression:
    def test_small_regression_within_threshold(self, detector):
        baseline = _snap({"accuracy": 1.0})
        current = _snap({"accuracy": 0.85})

        result = detector.check_release_gate(current, baseline)

        assert result["passed"] is True
        assert result["regressions"] == []

    def test_boundary_at_threshold(self, detector):
        baseline = _snap({"accuracy": 1.0})
        current = _snap({"accuracy": 0.80})

        result = detector.check_release_gate(current, baseline)

        assert result["passed"] is True
        assert result["regressions"] == []


class TestMissingBaseline:
    def test_missing_baseline_returns_none(self, detector):
        loaded = detector.load_baseline("nonexistent-id")
        assert loaded is None


class TestSaveLoad:
    def test_save_load_roundtrip(self, detector):
        snap = _snap(
            {"accuracy": 0.95, "recall": 0.88},
            snapshot_id="roundtrip",
            session_id="sess-42",
        )

        filepath = detector.save_snapshot(snap)
        assert os.path.exists(filepath)

        with open(filepath) as f:
            raw = json.load(f)
        assert raw["snapshot_id"] == "roundtrip"
        assert raw["session_id"] == "sess-42"
        assert raw["metrics"]["accuracy"] == 0.95

        loaded = detector.load_baseline("roundtrip")
        assert loaded is not None
        assert loaded.snapshot_id == "roundtrip"
        assert loaded.timestamp == "2026-04-10T00:00:00Z"
        assert loaded.metrics == {"accuracy": 0.95, "recall": 0.88}
        assert loaded.session_id == "sess-42"

    def test_history_dir_created_on_save(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "c")
        det = RegressionDetector(history_dir=nested)
        snap = _snap({"x": 1.0}, snapshot_id="nested")
        det.save_snapshot(snap)
        assert os.path.isdir(nested)


class TestDetectRegressions:
    def test_new_metric_not_in_baseline_ignored(self, detector):
        baseline = _snap({"accuracy": 0.90})
        current = _snap({"accuracy": 0.90, "new_metric": 0.10})

        regressions = detector.detect_regressions(current, baseline)
        assert regressions == []

    def test_baseline_zero_skipped(self, detector):
        baseline = _snap({"accuracy": 0.0})
        current = _snap({"accuracy": 0.50})

        regressions = detector.detect_regressions(current, baseline)
        assert regressions == []

    def test_multiple_regressions(self, detector):
        baseline = _snap({"accuracy": 1.0, "recall": 1.0, "f1": 1.0})
        current = _snap({"accuracy": 0.5, "recall": 0.5, "f1": 0.95})

        regressions = detector.detect_regressions(current, baseline)
        regressed_metrics = {r["metric"] for r in regressions}
        assert regressed_metrics == {"accuracy", "recall"}
        assert "f1" not in regressed_metrics
