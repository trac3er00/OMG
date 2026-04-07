from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Protocol, cast


class CorrectionCandidateProtocol(Protocol):
    correction_type: str
    description: str
    location: str
    severity: str
    suggested_fix: str
    confidence: float


class CorrectionCandidateCtor(Protocol):
    def __call__(
        self,
        *,
        correction_type: str,
        description: str,
        location: str,
        severity: str = "medium",
        suggested_fix: str = "",
        confidence: float = 0.8,
    ) -> CorrectionCandidateProtocol: ...


class SelfCorrectionResultProtocol(Protocol):
    candidates: list[CorrectionCandidateProtocol]
    corrections_applied: int

    @property
    def has_issues(self) -> bool: ...


class SelfCorrectionLoopProtocol(Protocol):
    def __init__(self, max_iterations: int = 3) -> None: ...

    def analyze(
        self, output: str, context: dict[str, object]
    ) -> SelfCorrectionResultProtocol: ...

    def should_iterate(self, result: SelfCorrectionResultProtocol) -> bool: ...

    def escalate(self, reason: str = "max iterations reached") -> dict[str, object]: ...

    def run_correction_cycle(
        self,
        code_file: str,
        test_command: str | None = None,
        context: dict[str, object] | None = None,
    ) -> SelfCorrectionResultProtocol: ...

    def run(
        self,
        code_file: str,
        test_command: str,
        ledger: object | None = None,
    ) -> dict[str, object]: ...

    def get_summary(self) -> dict[str, object]: ...


MODULE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "self_correction.py"
SPEC = importlib.util.spec_from_file_location("task46_self_correction", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
CorrectionCandidate = cast(CorrectionCandidateCtor, MODULE.CorrectionCandidate)
SelfCorrectionLoop = cast(type[SelfCorrectionLoopProtocol], MODULE.SelfCorrectionLoop)


class TestAnalyze:
    def test_detects_error_in_output(self) -> None:
        loop = SelfCorrectionLoop()
        result = loop.analyze(
            "Traceback (most recent call last):\nTypeError: bad type",
            {"file": "foo.py"},
        )
        assert result.has_issues
        assert any(c.severity in ("high", "critical") for c in result.candidates)

    def test_no_issues_on_clean_output(self) -> None:
        loop = SelfCorrectionLoop()
        result = loop.analyze("1 passed in 0.01s", {})
        assert not result.has_issues


class TestShouldIterate:
    def test_returns_false_at_max_iterations(self) -> None:
        loop = SelfCorrectionLoop(max_iterations=1)
        result = loop.analyze("Traceback\nTraceback", {"file": "x.py"})
        assert not loop.should_iterate(result)

    def test_returns_true_with_high_severity_under_max(self) -> None:
        loop = SelfCorrectionLoop(max_iterations=5)
        result = loop.analyze("Traceback\nTraceback", {"file": "x.py"})
        assert loop.should_iterate(result)


class TestEscalate:
    def test_escalate_returns_structured_dict(self) -> None:
        loop = SelfCorrectionLoop()
        result = loop.escalate("test failure")
        assert result["escalated"] is True
        assert "reason" in result
        assert "iterations_attempted" in result


class TestRunCorrectionCycle:
    def test_applies_missing_import_fix(self) -> None:
        loop = SelfCorrectionLoop()
        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w"
        ) as handle:
            _ = handle.write("print('hello')\n")
            code_path = handle.name
        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w"
        ) as handle:
            _ = handle.write("import missing_module_for_task_46\n")
            script_path = handle.name

        try:
            result = loop.run_correction_cycle(code_path, f"python3 {script_path}")
            assert result.has_issues
            assert result.corrections_applied == 1
            with open(code_path, encoding="utf-8") as handle:
                content = handle.read()
            assert content.startswith("import missing_module_for_task_46\n")
        finally:
            os.unlink(code_path)
            os.unlink(script_path)


class TestRun:
    def test_escalates_after_max_iterations_on_unfixable_error(self) -> None:
        loop = SelfCorrectionLoop(max_iterations=2)
        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w"
        ) as handle:
            _ = handle.write("def foo():\n    return 1 / 0\n")
            tmp_path = handle.name

        try:
            result = loop.run(tmp_path, "python3 -c raise RuntimeError")
            assert "iterations" in result or "escalated" in result
            assert result.get("escalated") is True
        finally:
            os.unlink(tmp_path)

    def test_get_summary_returns_expected_keys(self) -> None:
        loop = SelfCorrectionLoop()
        summary = loop.get_summary()
        assert "iterations" in summary
        assert "total_issues_found" in summary
        assert "total_corrections_applied" in summary
        assert "converged" in summary

    def test_run_stops_when_output_is_clean(self) -> None:
        loop = SelfCorrectionLoop(max_iterations=3)
        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w"
        ) as handle:
            _ = handle.write("print('ok')\n")
            tmp_path = handle.name

        try:
            result = loop.run(tmp_path, "python3 -c pass")
            assert result["iterations"] == 1
            assert result["converged"] is True
        finally:
            os.unlink(tmp_path)


def test_result_serialization_uses_candidate_fields() -> None:
    candidate = CorrectionCandidate(
        correction_type="type_error",
        description="desc",
        location="file.py",
    )
    payload = candidate.__dict__.copy()
    assert payload["correction_type"] == "type_error"
