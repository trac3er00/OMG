"""Tests for shadow manager and evidence helpers."""

from pathlib import Path

from hooks.shadow_manager import (
    begin_shadow_run,
    record_shadow_write,
    create_evidence_pack,
    has_recent_evidence,
    apply_shadow,
)


def test_shadow_run_records_file_and_evidence(tmp_path: Path):
    project = tmp_path
    src = project / "src"
    src.mkdir()
    file_path = src / "a.txt"
    file_path.write_text("hello", encoding="utf-8")

    run_id = begin_shadow_run(str(project), metadata={"test": True})
    entry = record_shadow_write(str(project), run_id, str(file_path))
    assert entry["file"] == "src/a.txt"

    ev_path = create_evidence_pack(
        str(project),
        run_id,
        tests=[{"name": "unit", "exit": 0}],
        security_scans=[],
        diff_summary={"files": 1},
        reproducibility={"cmd": "pytest"},
        unresolved_risks=[],
    )
    assert Path(ev_path).exists()
    assert has_recent_evidence(str(project)) is True


def test_shadow_apply_copies_overlay(tmp_path: Path):
    project = tmp_path
    src = project / "src"
    src.mkdir()
    file_path = src / "b.txt"
    file_path.write_text("v1", encoding="utf-8")

    run_id = begin_shadow_run(str(project))
    record_shadow_write(str(project), run_id, str(file_path))
    # mutate source after snapshot
    file_path.write_text("v2", encoding="utf-8")

    result = apply_shadow(str(project), run_id)
    assert "src/b.txt" in result["applied"]
    assert file_path.read_text(encoding="utf-8") == "v1"
