from __future__ import annotations
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAny=false

from pathlib import Path

from pytest import MonkeyPatch

from runtime import red_team_interactive
from runtime.red_team_interactive import (
    ReviewSession,
    interactive_review,
    load_false_positives,
    save_false_positive,
    scan_file,
)


def test_interactive_review_returns_session_payload(
    tmp_path: Path, monkeypatch: MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    _ = (tmp_path / "src" / "clean.py").write_text("print('safe')\n", encoding="utf-8")

    session: ReviewSession = interactive_review(".", auto_mode=True)

    assert session["finding_count"] >= 0
    assert isinstance(session["findings"], list)
    assert session["false_positives_marked"] == 0
    assert session["scanned_files"] == 1


def test_scan_file_detects_eval_usage(tmp_path: Path):
    candidate = tmp_path / "danger.py"
    _ = candidate.write_text("result = eval(user_input)\n", encoding="utf-8")

    findings = scan_file(str(candidate))

    assert any(finding["id"] == "eval-usage" for finding in findings)
    assert findings[0]["line"] == 1


def test_load_false_positives_returns_empty_set_without_database(
    tmp_path: Path, monkeypatch: MonkeyPatch
):
    fp_path = tmp_path / ".omg" / "state" / "red-team-fp.json"
    monkeypatch.setattr(red_team_interactive, "FP_DATABASE_PATH", str(fp_path))

    assert load_false_positives() == set()


def test_save_false_positive_persists_to_database(
    tmp_path: Path, monkeypatch: MonkeyPatch
):
    fp_path = tmp_path / ".omg" / "state" / "red-team-fp.json"
    monkeypatch.setattr(red_team_interactive, "FP_DATABASE_PATH", str(fp_path))

    save_false_positive("sql-injection:test.py:10")

    assert load_false_positives() == {"sql-injection:test.py:10"}
    assert fp_path.exists()


def test_interactive_review_writes_report_file(
    tmp_path: Path, monkeypatch: MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    _ = (tmp_path / "src" / "danger.py").write_text(
        "result = eval(user_input)\n", encoding="utf-8"
    )

    session: ReviewSession = interactive_review(".", auto_mode=True)

    report_path = Path(session["report_path"])
    assert report_path.exists()
    assert session["finding_count"] == 1


def test_interactive_review_filters_persisted_false_positives(
    tmp_path: Path, monkeypatch: MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    fp_path = tmp_path / ".omg" / "state" / "red-team-fp.json"
    monkeypatch.setattr(red_team_interactive, "FP_DATABASE_PATH", str(fp_path))
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "danger.py"
    _ = source.write_text("result = eval(user_input)\n", encoding="utf-8")
    save_false_positive(f"eval-usage:{source}:1")

    session: ReviewSession = interactive_review(".", auto_mode=True)

    assert session["finding_count"] == 0
    assert session["findings"] == []
