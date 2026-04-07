from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Callable, Protocol, TypedDict, cast

import pytest


class ProofScoreBreakdown(TypedDict):
    completeness: float
    validity: float
    diversity: float
    traceability: float


class ProofScoreResult(TypedDict):
    score: int
    band: str
    breakdown: ProofScoreBreakdown


class InstantSuccessResult(TypedDict):
    success: bool
    type: str
    confidence: float
    target_dir: str
    file_count: int
    pack_loaded: bool
    evidence: dict[str, ProofScoreResult]
    silent_safety: bool
    silent_safety_restored: str | None


class InstantSuccessWithWarningResult(InstantSuccessResult, total=False):
    warning: str
    subdirectory: str


class InstantClarificationResult(TypedDict):
    success: bool
    type: str
    confidence: float
    clarification_needed: bool
    clarification_prompt: str | None


InstantResult = InstantSuccessWithWarningResult | InstantClarificationResult


class RunInstantFn(Protocol):
    def __call__(
        self,
        prompt: str,
        target_dir: str,
        on_progress: Callable[[dict[str, str]], None] | None = None,
    ) -> InstantResult: ...


run_instant = cast(
    RunInstantFn, getattr(import_module("runtime.instant_mode"), "run_instant")
)


def _run_success(prompt: str, target_dir: str) -> InstantSuccessWithWarningResult:
    return cast(InstantSuccessWithWarningResult, run_instant(prompt, target_dir))


def _run_clarification(prompt: str, target_dir: str) -> InstantClarificationResult:
    return cast(InstantClarificationResult, run_instant(prompt, target_dir))


def test_run_instant_generates_landing_scaffold(tmp_path: Path) -> None:
    result = _run_success("make a landing page", str(tmp_path))

    assert result["success"] is True
    assert result["type"] == "landing"
    assert result["file_count"] > 0
    assert Path(result["target_dir"]).exists()


def test_run_instant_supports_korean_landing_prompt(tmp_path: Path) -> None:
    result = _run_success("랜딩페이지 만들어줘", str(tmp_path))

    assert result["success"] is True
    assert result["type"] == "landing"
    assert result["file_count"] > 0


def test_run_instant_returns_clarification_for_ambiguous_prompt(tmp_path: Path) -> None:
    result = _run_clarification("뭔가 만들어줘", str(tmp_path))

    assert result["success"] is False
    assert result["clarification_needed"] is True
    assert isinstance(result["clarification_prompt"], str)
    assert result["clarification_prompt"]


def test_run_instant_uses_subdirectory_for_non_empty_target(tmp_path: Path) -> None:
    _ = (tmp_path / "existing.txt").write_text("keep", encoding="utf-8")

    result = _run_success("make a landing page", str(tmp_path))

    assert result["success"] is True
    assert result["target_dir"] != str(tmp_path)
    assert Path(result["target_dir"]).parent == tmp_path
    assert result.get("warning") or result.get("subdirectory")


def test_run_instant_emits_progress_events(tmp_path: Path) -> None:
    events: list[dict[str, str]] = []

    result = cast(
        InstantSuccessWithWarningResult,
        run_instant(
            "make a landing page",
            str(tmp_path),
            on_progress=events.append,
        ),
    )

    assert result["success"] is True
    assert len(events) >= 4
    assert events[0]["phase"] == "classify"
    assert events[-1]["phase"] == "done"
    assert all({"phase", "message"} <= set(event) for event in events)


def test_run_instant_generates_api_scaffold(tmp_path: Path) -> None:
    result = _run_success("make an API", str(tmp_path))

    assert result["success"] is True
    assert result["type"] == "api"
    assert result["file_count"] > 0


def test_run_instant_treats_generic_site_prompt_as_landing(tmp_path: Path) -> None:
    result = _run_success("사이트 만들어줘", str(tmp_path))

    assert result["success"] is True
    assert result["type"] == "landing"


def test_run_instant_includes_proof_score(tmp_path: Path) -> None:
    result = _run_success("make a landing page", str(tmp_path))

    assert result["success"] is True
    assert result["evidence"]["proofScore"]["score"] >= 0
    assert result["evidence"]["proofScore"]["band"] in {
        "weak",
        "developing",
        "strong",
        "complete",
    }


def test_run_instant_restores_silent_safety_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SILENT_SAFETY", "preserve-me")

    result = _run_success("make a landing page", str(tmp_path))

    assert result["success"] is True
    assert result["silent_safety"] is True
    assert result["silent_safety_restored"] == "preserve-me"
