"""Reproducible evaluation results for release gating."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import platform
import socket
from typing import Any, Optional
from uuid import uuid4


EVAL_GATE_LATEST_REL_PATH = Path(".omg") / "evals" / "latest.json"
EVAL_GATE_HISTORY_REL_PATH = Path(".omg") / "evals" / "history.jsonl"
EVAL_GATE_TRACE_LINKS_REL_PATH = Path(".omg") / "evals" / "trace-links.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _executor() -> dict[str, str | int]:
    return {
        "user": getpass.getuser(),
        "pid": os.getpid(),
    }


def _environment() -> dict[str, str]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
    }


def evaluate_trace(
    project_dir: str,
    *,
    trace_id: str,
    suites: list[str],
    metrics: dict[str, float],
    lineage: dict[str, Any] | None = None,
    regression_threshold: float = 0.95,
) -> dict[str, Any]:
    eval_id = f"eval-{uuid4().hex}"
    scorecard = {name: float(metrics.get(name, 0.0)) for name in suites}
    regressed = any(score < regression_threshold for score in scorecard.values())
    result = {
        "schema": "EvalGateResult",
        "eval_id": eval_id,
        "trace_id": trace_id,
        "lineage": lineage or {},
        "evaluated_at": _now(),
        "timestamp": _now(),
        "executor": _executor(),
        "environment": _environment(),
        "status": "fail" if regressed else "ok",
        "suites": suites,
        "metrics": scorecard,
        "summary": {
            "regressed": regressed,
            "regression_threshold": regression_threshold,
        },
    }

    latest_path = Path(project_dir) / EVAL_GATE_LATEST_REL_PATH
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    _ = latest_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    _ = link_trace(project_dir, eval_id=eval_id, trace_id=trace_id)

    history_path = Path(project_dir) / EVAL_GATE_HISTORY_REL_PATH
    with history_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(result, ensure_ascii=True) + "\n")

    result["path"] = EVAL_GATE_LATEST_REL_PATH.as_posix()
    return result


def link_trace(project_dir: str, *, eval_id: str, trace_id: str) -> dict[str, Any]:
    link = {
        "schema": "EvalTraceLink",
        "eval_id": eval_id,
        "trace_id": trace_id,
        "timestamp": _now(),
        "executor": _executor(),
        "environment": _environment(),
    }
    path = Path(project_dir) / EVAL_GATE_TRACE_LINKS_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(link, ensure_ascii=True) + "\n")
    link["path"] = EVAL_GATE_TRACE_LINKS_REL_PATH.as_posix()
    return link


@dataclass
class EvalSnapshot:
    """Point-in-time eval metrics snapshot."""

    snapshot_id: str
    timestamp: str
    metrics: dict[str, float]
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class RegressionDetector:
    """Detects eval metric regressions against historical baseline."""

    def __init__(
        self,
        history_dir: str = ".omg/eval-history",
        regression_threshold: float = 0.2,
    ):
        self.history_dir = history_dir
        self.regression_threshold = regression_threshold

    def save_snapshot(self, snapshot: EvalSnapshot) -> str:
        """Save eval snapshot to history. Returns file path."""
        os.makedirs(self.history_dir, exist_ok=True)
        filepath = os.path.join(self.history_dir, f"eval-{snapshot.snapshot_id}.json")
        with open(filepath, "w") as f:
            json.dump(snapshot.to_dict(), f, indent=2)
        return filepath

    def load_baseline(self, baseline_id: str) -> Optional[EvalSnapshot]:
        """Load a historical baseline snapshot."""
        filepath = os.path.join(self.history_dir, f"eval-{baseline_id}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath) as f:
            data = json.load(f)
        return EvalSnapshot(**data)

    def detect_regressions(
        self, current: EvalSnapshot, baseline: EvalSnapshot
    ) -> list[dict]:
        """
        Compare current metrics against baseline.
        Returns list of regression dicts for metrics that regressed beyond threshold.
        """
        regressions = []
        for metric, current_val in current.metrics.items():
            if metric not in baseline.metrics:
                continue
            baseline_val = baseline.metrics[metric]
            if baseline_val == 0:
                continue
            regression_pct = (baseline_val - current_val) / baseline_val
            if regression_pct > self.regression_threshold:
                regressions.append(
                    {
                        "metric": metric,
                        "baseline": baseline_val,
                        "current": current_val,
                        "regression_pct": regression_pct,
                    }
                )
        return regressions

    def check_release_gate(
        self, current: EvalSnapshot, baseline: EvalSnapshot
    ) -> dict:
        """Run release gate check. Returns gate result dict."""
        regressions = self.detect_regressions(current, baseline)
        return {
            "passed": len(regressions) == 0,
            "regressions": regressions,
            "message": (
                "All eval metrics within threshold"
                if not regressions
                else (
                    f"{len(regressions)} metric(s) regressed beyond "
                    f"{self.regression_threshold * 100:.0f}% threshold"
                )
            ),
        }


# ---------------------------------------------------------------------------
# Session trajectory tracking
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryEntry:
    tool: str
    decision: str
    outcome: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: Optional[str] = None


class TrajectoryTracker:
    """Tracks session tool calls and decisions as a trajectory."""

    def __init__(self, session_id: str, output_dir: str = ".omg/eval-history"):
        self.session_id = session_id
        self.output_dir = output_dir
        self.entries: list[TrajectoryEntry] = []

    def record(self, tool: str, decision: str, outcome: str) -> None:
        entry = TrajectoryEntry(
            tool=tool, decision=decision, outcome=outcome, session_id=self.session_id
        )
        self.entries.append(entry)

    def export_jsonl(self) -> str:
        """Export trajectory as JSONL file. Returns file path."""
        os.makedirs(self.output_dir, exist_ok=True)
        filename = f"trajectory-{self.session_id}.jsonl"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(json.dumps(asdict(entry), ensure_ascii=True) + "\n")
        return filepath

    def to_ci_artifact(self) -> dict[str, Any]:
        """Format trajectory as CI artifact metadata."""
        return {
            "session_id": self.session_id,
            "entry_count": len(self.entries),
            "filepath": os.path.join(
                self.output_dir, f"trajectory-{self.session_id}.jsonl"
            ),
            "tools_used": sorted({e.tool for e in self.entries}),
        }
