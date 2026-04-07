from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, TypedDict


class CorrectionCandidatePayload(TypedDict):
    type: str
    description: str
    location: str
    severity: str
    fix: str
    confidence: float


class SelfCorrectionPayload(TypedDict):
    total_issues: int
    corrections_applied: int
    candidates: list[CorrectionCandidatePayload]


class SelfCorrectionSummary(TypedDict):
    iterations: int
    total_issues_found: int
    total_corrections_applied: int
    converged: bool


class SelfCorrectionEscalation(TypedDict):
    escalated: bool
    reason: str
    iterations_attempted: int
    summary: SelfCorrectionSummary


class LedgerAppendable(Protocol):
    def append(self, entry: object) -> object: ...


def _context_location(context: Mapping[str, object]) -> str:
    location = context.get("file", "unknown")
    return location if isinstance(location, str) else "unknown"


CORRECTION_TYPES = (
    "type_error",
    "logic_error",
    "style_violation",
    "missing_test",
    "scope_drift",
)


@dataclass
class CorrectionCandidate:
    correction_type: str
    description: str
    location: str
    severity: str = "medium"
    suggested_fix: str = ""
    confidence: float = 0.8


@dataclass
class SelfCorrectionResult:
    candidates: list[CorrectionCandidate] = field(default_factory=list)
    corrections_applied: int = 0
    total_issues: int = 0

    @property
    def has_issues(self) -> bool:
        return len(self.candidates) > 0

    def to_dict(self) -> SelfCorrectionPayload:
        return {
            "total_issues": len(self.candidates),
            "corrections_applied": self.corrections_applied,
            "candidates": [
                {
                    "type": c.correction_type,
                    "description": c.description,
                    "location": c.location,
                    "severity": c.severity,
                    "fix": c.suggested_fix,
                    "confidence": c.confidence,
                }
                for c in self.candidates
            ],
        }


class SelfCorrectionLoop:
    def __init__(self, max_iterations: int = 3) -> None:
        self.max_iterations: int = max_iterations
        self._iteration_count: int = 0
        self._escalated: bool = False
        self._history: list[SelfCorrectionResult] = []

    def analyze(
        self, output: str, context: Mapping[str, object] | None = None
    ) -> SelfCorrectionResult:
        candidates: list[CorrectionCandidate] = []
        ctx = context or {}

        if "error" in output.lower() or "traceback" in output.lower():
            candidates.append(
                CorrectionCandidate(
                    correction_type="type_error",
                    description="Error detected in output",
                    location=_context_location(ctx),
                    severity="high",
                    suggested_fix="Check error message and fix root cause",
                    confidence=0.9,
                )
            )

        if "todo" in output.lower() or "fixme" in output.lower():
            candidates.append(
                CorrectionCandidate(
                    correction_type="logic_error",
                    description="TODO/FIXME placeholder found — implementation incomplete",
                    location=_context_location(ctx),
                    severity="medium",
                    suggested_fix="Complete the TODO/FIXME implementation",
                    confidence=0.85,
                )
            )

        if ctx.get("test_count", 1) == 0:
            candidates.append(
                CorrectionCandidate(
                    correction_type="missing_test",
                    description="No tests found for this change",
                    location=_context_location(ctx),
                    severity="medium",
                    suggested_fix="Add unit tests for the new functionality",
                    confidence=0.75,
                )
            )

        result = SelfCorrectionResult(candidates=candidates)
        self._history.append(result)
        self._iteration_count += 1
        return result

    def should_iterate(self, result: SelfCorrectionResult) -> bool:
        return (
            result.has_issues
            and self._iteration_count < self.max_iterations
            and any(c.severity in ("high", "critical") for c in result.candidates)
        )

    def record_correction(self, _correction_type: str, applied: bool = True) -> None:
        if self._history and applied:
            self._history[-1].corrections_applied += 1

    def get_summary(self) -> SelfCorrectionSummary:
        total_issues = sum(len(r.candidates) for r in self._history)
        total_corrections = sum(r.corrections_applied for r in self._history)
        return {
            "iterations": self._iteration_count,
            "total_issues_found": total_issues,
            "total_corrections_applied": total_corrections,
            "converged": not (self._history and self._history[-1].has_issues),
        }

    def run_correction_cycle(
        self,
        code_file: str,
        test_command: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> SelfCorrectionResult:
        ctx = context or {}
        output = ""

        if test_command:
            try:
                proc = subprocess.run(
                    test_command.split(),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = proc.stdout + proc.stderr
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                output = str(exc)

        result = self.analyze(output, {"file": code_file, **ctx})

        if result.has_issues and code_file and os.path.exists(code_file):
            for candidate in result.candidates:
                if (
                    candidate.correction_type == "type_error"
                    and "ModuleNotFoundError" in output
                ):
                    match = re.search(r"No module named '([^']+)'", output)
                    if match:
                        module = match.group(1)
                        self._apply_import_fix(code_file, module)
                        result.corrections_applied += 1
                        candidate.suggested_fix = f"Added: import {module}"

        return result

    def _apply_import_fix(self, code_file: str, module: str) -> None:
        try:
            with open(code_file, encoding="utf-8") as handle:
                content = handle.read()

            import_line = f"import {module}\n"
            if import_line not in content:
                with open(code_file, "w", encoding="utf-8") as handle:
                    _ = handle.write(import_line + content)
        except OSError:
            pass

    def escalate(
        self, reason: str = "max iterations reached"
    ) -> SelfCorrectionEscalation:
        self._escalated = True
        return {
            "escalated": True,
            "reason": reason,
            "iterations_attempted": self._iteration_count,
            "summary": self.get_summary(),
        }

    def run(
        self,
        code_file: str,
        test_command: str,
        ledger: LedgerAppendable | None = None,
    ) -> SelfCorrectionSummary | SelfCorrectionEscalation:
        self._escalated = False

        with tempfile.TemporaryDirectory() as _temp_dir:
            for i in range(self.max_iterations):
                result = self.run_correction_cycle(code_file, test_command)

                if ledger is not None:
                    try:
                        _ = ledger.append(
                            {
                                "type": "self_correction",
                                "context": (
                                    f"cycle {i + 1}/{self.max_iterations} for {code_file}"
                                ),
                                "rationale": (
                                    f"Attempted {result.corrections_applied} corrections"
                                ),
                                "source": "agent",
                            }
                        )
                    except Exception:
                        pass

                if not result.has_issues:
                    break

                if not self.should_iterate(result):
                    break

        summary = self.get_summary()
        if (
            summary.get("converged") is False
            and self._iteration_count >= self.max_iterations
        ):
            return self.escalate()

        return summary
