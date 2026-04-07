from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, cast

import pytest


class ResumeResult(TypedDict):
    available: bool
    state: dict[str, object] | None
    reason: NotRequired[str]
    version: NotRequired[str | None]
    age_hours: NotRequired[float]


class AutoResumeModule(Protocol):
    HANDOFF_PATH: str
    STALENESS_DAYS: int
    time: object

    def save_handoff(self, state: dict[str, object]) -> None: ...

    def check_resume(self) -> ResumeResult: ...

    def clear_handoff(self) -> None: ...


auto_resume = cast(
    AutoResumeModule, cast(object, importlib.import_module("runtime.auto_resume"))
)


def test_save_handoff_creates_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff_path = tmp_path / ".omg" / "state" / "handoff-latest.json"
    monkeypatch.setattr(auto_resume, "HANDOFF_PATH", str(handoff_path))

    auto_resume.save_handoff({"decisions": ["use TDD"]})

    assert handoff_path.exists()


def test_check_resume_after_save_reports_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff_path = tmp_path / ".omg" / "state" / "handoff-latest.json"
    monkeypatch.setattr(auto_resume, "HANDOFF_PATH", str(handoff_path))

    auto_resume.save_handoff({"decisions": ["use TDD"]})

    result = auto_resume.check_resume()

    assert result["available"] is True
    assert result["state"] == {"decisions": ["use TDD"]}
    age_hours = result.get("age_hours")
    assert isinstance(age_hours, float)


def test_check_resume_without_file_reports_no_handoff_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff_path = tmp_path / ".omg" / "state" / "handoff-latest.json"
    monkeypatch.setattr(auto_resume, "HANDOFF_PATH", str(handoff_path))

    result = auto_resume.check_resume()

    assert result == {
        "available": False,
        "state": None,
        "reason": "no_handoff_found",
    }


def test_check_resume_with_stale_handoff_reports_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff_path = tmp_path / ".omg" / "state" / "handoff-latest.json"
    monkeypatch.setattr(auto_resume, "HANDOFF_PATH", str(handoff_path))
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    stale_saved_at = 100.0
    now = stale_saved_at + ((auto_resume.STALENESS_DAYS + 1) * 86400)
    monkeypatch.setattr(auto_resume.time, "time", lambda: now)
    _ = handoff_path.write_text(
        json.dumps(
            {
                "version": "3.0.0",
                "saved_at": stale_saved_at,
                "state": {"decisions": ["use TDD"]},
            }
        ),
        encoding="utf-8",
    )

    result = auto_resume.check_resume()

    assert result["available"] is False
    assert result["state"] is None
    reason = result.get("reason")
    assert isinstance(reason, str)
    assert "stale" in reason


def test_check_resume_returns_saved_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff_path = tmp_path / ".omg" / "state" / "handoff-latest.json"
    monkeypatch.setattr(auto_resume, "HANDOFF_PATH", str(handoff_path))
    state: dict[str, object] = {
        "decisions": ["use TDD"],
        "open_loops": ["add QA"],
    }

    auto_resume.save_handoff(state)

    result = auto_resume.check_resume()
    saved_state = result["state"]

    assert saved_state is not None
    assert saved_state["decisions"] == ["use TDD"]
    assert saved_state["open_loops"] == ["add QA"]


def test_clear_handoff_removes_saved_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff_path = tmp_path / ".omg" / "state" / "handoff-latest.json"
    monkeypatch.setattr(auto_resume, "HANDOFF_PATH", str(handoff_path))
    auto_resume.save_handoff({"decisions": ["use TDD"]})

    auto_resume.clear_handoff()

    assert not handoff_path.exists()
    assert auto_resume.check_resume() == {
        "available": False,
        "state": None,
        "reason": "no_handoff_found",
    }


def test_check_resume_with_invalid_json_reports_parse_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff_path = tmp_path / ".omg" / "state" / "handoff-latest.json"
    monkeypatch.setattr(auto_resume, "HANDOFF_PATH", str(handoff_path))
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    _ = handoff_path.write_text("{not-json", encoding="utf-8")

    result = auto_resume.check_resume()

    assert result["available"] is False
    assert result["state"] is None
    reason = result.get("reason")
    assert isinstance(reason, str)
    assert reason.startswith("parse_error:")


RetryBudget = auto_resume.RetryBudget  # type: ignore[attr-defined]
HandoffBudgetExceeded = auto_resume.HandoffBudgetExceeded  # type: ignore[attr-defined]
compact_context_for_retry = auto_resume.compact_context_for_retry  # type: ignore[attr-defined]
resume_with_retries = auto_resume.resume_with_retries  # type: ignore[attr-defined]


def test_retry_budget_prevents_infinite_loops() -> None:
    budget = RetryBudget(max_retries=3)

    assert budget.increment(token_cost=100) is True
    assert budget.increment(token_cost=100) is True
    assert budget.increment(token_cost=100) is True
    assert budget.increment(token_cost=100) is False

    assert budget.attempt_count == 4
    diag = budget.diagnostic()
    assert "4 attempts" in diag
    assert "max: 3" in diag


def test_retry_budget_health_metrics_on_success() -> None:
    budget = RetryBudget(max_retries=3)
    budget.increment(token_cost=500)
    budget.increment(token_cost=300)
    budget.success = True

    metrics = budget.health_metrics
    assert metrics["success"] is True
    assert metrics["attempt_count"] == 2
    assert metrics["token_waste"] == 500
    assert metrics["success_rate"] == pytest.approx(0.5)


def test_retry_budget_health_metrics_on_failure() -> None:
    budget = RetryBudget(max_retries=2)
    budget.increment(token_cost=400)
    budget.increment(token_cost=300)

    metrics = budget.health_metrics
    assert metrics["success"] is False
    assert metrics["token_waste"] == 700
    assert metrics["success_rate"] == 0.0


def test_retry_compaction_reduces_size() -> None:
    large_state: dict[str, object] = {
        "decisions": list(range(50)),
        "long_text": "x" * 5000,
        "small": "keep",
    }

    compacted = compact_context_for_retry(large_state)

    assert len(cast(list[object], compacted["decisions"])) == 10
    assert len(cast(str, compacted["long_text"])) == 2000
    assert compacted["small"] == "keep"
    assert compacted["_compacted"] is True

    original_size = len(json.dumps(large_state, default=str))
    compacted_size = len(json.dumps(compacted, default=str))
    assert compacted_size < original_size


def test_resume_with_retries_succeeds_first_try() -> None:
    state: dict[str, object] = {"goal": "test"}

    def handler(s: dict[str, object]) -> dict[str, object]:
        return {"done": True}

    result = resume_with_retries(state, handler, max_retries=3)
    assert result["done"] is True
    metrics = result["_health_metrics"]
    assert isinstance(metrics, dict)
    assert metrics["success"] is True
    assert metrics["attempt_count"] == 1


def test_resume_with_retries_succeeds_on_second_try() -> None:
    call_count = 0

    def handler(s: dict[str, object]) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("transient")
        return {"done": True}

    result = resume_with_retries({"goal": "test"}, handler, max_retries=3)
    assert result["done"] is True
    assert result["_health_metrics"]["attempt_count"] == 2


def test_resume_with_retries_raises_on_budget_exceeded() -> None:
    def always_fail(s: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("always fails")

    with pytest.raises(HandoffBudgetExceeded, match="3 attempts"):
        resume_with_retries({"goal": "test"}, always_fail, max_retries=2)


def test_resume_with_retries_compacts_between_attempts() -> None:
    states_seen: list[dict[str, object]] = []

    def handler(s: dict[str, object]) -> dict[str, object]:
        states_seen.append(dict(s))
        if len(states_seen) < 2:
            raise RuntimeError("retry")
        return {"done": True}

    resume_with_retries({"data": list(range(50))}, handler, max_retries=3)
    assert "_compacted" not in states_seen[0]
    assert states_seen[1].get("_compacted") is True
