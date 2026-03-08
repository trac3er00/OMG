"""Tests for shadow manager and evidence helpers."""

import json
from pathlib import Path

import pytest

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


def test_create_evidence_pack_rejects_path_escape_run_id(tmp_path: Path):
    with pytest.raises(ValueError, match="run_id"):
        create_evidence_pack(
            str(tmp_path),
            "../../pwned",
            tests=[],
            security_scans=[],
            diff_summary={},
            reproducibility={},
            unresolved_risks=[],
        )


def test_create_evidence_pack_includes_optional_sibling_artifacts_when_provided(tmp_path: Path):
    run_id = begin_shadow_run(str(tmp_path))
    ev_path = create_evidence_pack(
        str(tmp_path),
        run_id,
        tests=[],
        security_scans=[],
        diff_summary={},
        reproducibility={},
        unresolved_risks=[],
        claims=[{"claim_type": "release_ready"}],
        test_delta={"added": ["tests/test_new.py"]},
        browser_evidence_path=".omg/evidence/browser-evidence.json",
        repro_pack_path=".omg/evidence/repro-pack.json",
    )

    payload = json.loads(Path(ev_path).read_text(encoding="utf-8"))
    assert payload["claims"] == [{"claim_type": "release_ready"}]
    assert payload["test_delta"] == {"added": ["tests/test_new.py"]}
    assert payload["browser_evidence_path"] == ".omg/evidence/browser-evidence.json"
    assert payload["repro_pack_path"] == ".omg/evidence/repro-pack.json"


def test_create_evidence_pack_omits_optional_sibling_artifacts_when_not_provided(tmp_path: Path):
    run_id = begin_shadow_run(str(tmp_path))
    ev_path = create_evidence_pack(
        str(tmp_path),
        run_id,
        tests=[],
        security_scans=[],
        diff_summary={},
        reproducibility={},
        unresolved_risks=[],
    )

    payload = json.loads(Path(ev_path).read_text(encoding="utf-8"))
    assert "claims" not in payload
    assert "test_delta" not in payload
    assert "browser_evidence_path" not in payload
    assert "repro_pack_path" not in payload
