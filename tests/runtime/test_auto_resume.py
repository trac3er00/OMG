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
