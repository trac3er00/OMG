"""Local model runtime adapter (v1 stub)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class LocalAdapter:
    runtime = "local"

    def plan(self, idea: dict[str, Any]) -> dict[str, Any]:
        goal = str(idea.get("goal", "")).strip() or "unspecified-goal"
        return {
            "runtime": self.runtime,
            "phase": "plan",
            "status": "planned",
            "goal": goal,
            "steps": ["analyze-goal", "generate-plan", "emit-checklist"],
        }

    def execute(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "phase": "execute",
            "status": "executed",
            "worker_mode": "stub",
            "operations": ["apply-plan", "collect-diff"],
            "errors": [],
        }

    def verify(self, execution_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "phase": "verify",
            "status": "verified",
            "ok": True,
            "checks": [
                {"name": "tests", "passed": True},
                {"name": "security", "passed": True},
                {"name": "worker_implementation", "passed": False, "mode": "stub"},
            ],
        }

    def collect_evidence(self, verify_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "phase": "evidence",
            "status": "collected",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tests": verify_result.get("checks", []),
            "security_scans": [],
            "diff_summary": {},
            "reproducibility": {"seed": "deterministic"},
            "unresolved_risks": [],
            "worker_mode": "stub",
        }
