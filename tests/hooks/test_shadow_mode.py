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


def test_auto_journal_mutation_creates_journal_entry_for_write(tmp_path: Path):
    from hooks.shadow_manager import auto_journal_mutation

    target = tmp_path / "src" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")

    run_id = begin_shadow_run(str(tmp_path))
    record_shadow_write(str(tmp_path), run_id, str(target))

    result = auto_journal_mutation(str(tmp_path), "Write", str(target), run_id)

    assert result is not None
    assert result["status"] == "recorded"
    assert result["rollback_mode"] in {"branch+journal+repro", "journal+repro"}

    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    entries = list(journal_dir.glob("*.json"))
    assert len(entries) >= 1

    payload = json.loads(entries[-1].read_text(encoding="utf-8"))
    assert payload["tool"] == "write"
    assert payload["metadata"]["file_path"] == str(target)
    assert payload["run_id"] == run_id


def test_auto_journal_mutation_creates_journal_entry_for_edit(tmp_path: Path):
    from hooks.shadow_manager import auto_journal_mutation

    target = tmp_path / "lib.py"
    target.write_text("y = 2\n", encoding="utf-8")

    run_id = begin_shadow_run(str(tmp_path))
    record_shadow_write(str(tmp_path), run_id, str(target))

    result = auto_journal_mutation(str(tmp_path), "Edit", str(target), run_id)

    assert result is not None
    assert result["status"] == "recorded"

    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    entries = list(journal_dir.glob("*.json"))
    payload = json.loads(entries[-1].read_text(encoding="utf-8"))
    assert payload["tool"] == "edit"
    assert payload["run_id"] == run_id


def test_auto_journal_mutation_creates_journal_entry_for_multiedit(tmp_path: Path):
    from hooks.shadow_manager import auto_journal_mutation

    target = tmp_path / "multi.py"
    target.write_text("z = 3\n", encoding="utf-8")

    run_id = begin_shadow_run(str(tmp_path))
    record_shadow_write(str(tmp_path), run_id, str(target))

    result = auto_journal_mutation(str(tmp_path), "MultiEdit", str(target), run_id)

    assert result is not None
    assert result["status"] == "recorded"

    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    entries = list(journal_dir.glob("*.json"))
    payload = json.loads(entries[-1].read_text(encoding="utf-8"))
    assert payload["tool"] == "multiedit"
    assert payload["run_id"] == run_id


def test_auto_journal_mutation_not_triggered_for_read(tmp_path: Path):
    from hooks.shadow_manager import _handle_post_tool_use

    import hooks.shadow_manager as sm
    original = sm._project_dir
    sm._project_dir = lambda: str(tmp_path)
    try:
        _handle_post_tool_use({
            "tool_name": "Read",
            "tool_input": {"file_path": "README.md"},
        })
    finally:
        sm._project_dir = original

    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    assert not journal_dir.exists() or len(list(journal_dir.glob("*.json"))) == 0
