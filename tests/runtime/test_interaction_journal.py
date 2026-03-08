from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.interaction_journal import InteractionJournal


def test_record_step_persists_journal_entry(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("hello\n", encoding="utf-8")
    journal = InteractionJournal(str(tmp_path))

    event = journal.record_step("write", {"file": "README.md"})
    step_path = tmp_path / ".omg" / "state" / "interaction_journal" / f"{event['step_id']}.json"

    assert event["status"] == "recorded"
    assert event["rollback_mode"] in {"branch+journal+repro", "journal+repro"}
    assert step_path.exists()

    payload = json.loads(step_path.read_text(encoding="utf-8"))
    assert payload["tool"] == "write"
    assert payload["metadata"]["file"] == "README.md"
    assert payload["shadow_manifest_path"].endswith("manifest.json")


def test_undo_returns_unsupported_for_external_bash_step(tmp_path: Path) -> None:
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step("bash", {"command": "npm publish", "side_effect_scope": "external"})
    assert event["rollback_mode"] == "unsupported"

    result = journal.undo(cast(str, event["step_id"]))

    assert result["status"] == "unsupported"
    assert result["reason"] == "external side effect scope"
    assert result["manifest_path"]


def test_undo_write_restores_file_with_real_shadow_restore(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("v1\n", encoding="utf-8")
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step("write", {"file": "README.md"})
    target.write_text("v2\n", encoding="utf-8")
    result = journal.undo(cast(str, event["step_id"]))

    assert result["status"] == "ok"
    assert target.read_text(encoding="utf-8") == "v1\n"


def test_undo_latest_no_entries_is_noop(tmp_path: Path) -> None:
    journal = InteractionJournal(str(tmp_path))

    result = journal.undo("")

    assert result == {"status": "noop", "reason": "no journal entries"}


# --- Auto-journaling tests (Task 4) ---


def test_auto_journal_write_includes_run_id_and_shadow_manifest(tmp_path: Path) -> None:
    """Mutating write creates journal entry with run_id and shadow manifest."""
    target = tmp_path / "app.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    evidence_path = tmp_path / ".omg" / "evidence" / "test-run-001.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(
            {
                "schema": "EvidencePack",
                "run_id": "test-run-001",
                "security_scans": [],
                "trace_ids": [],
                "lineage": {},
                "artifacts": [],
                "unresolved_risks": [],
            }
        ),
        encoding="utf-8",
    )
    journal = InteractionJournal(str(tmp_path))

    run_id = "test-run-001"
    event = journal.record_step("write", {"file": "app.py", "run_id": run_id})

    step_path = tmp_path / ".omg" / "state" / "interaction_journal" / f"{event['step_id']}.json"
    payload = json.loads(step_path.read_text(encoding="utf-8"))

    assert payload["metadata"]["run_id"] == run_id
    assert payload["run_id"] == run_id
    assert payload["shadow_manifest_path"].endswith("manifest.json")
    assert event["status"] == "recorded"
    assert event["repro_pointer"] == ".omg/evidence/repro-pack-test-run-001.json"


def test_auto_journal_multiedit_gets_rollback_and_shadow(tmp_path: Path) -> None:
    """MultiEdit operations get rollback mode and shadow manifest like write/edit."""
    target = tmp_path / "config.py"
    target.write_text("x = 1\n", encoding="utf-8")
    journal = InteractionJournal(str(tmp_path))

    event = journal.record_step("multiedit", {"file": "config.py"})

    assert event["rollback_mode"] in {"branch+journal+repro", "journal+repro"}
    step_path = tmp_path / ".omg" / "state" / "interaction_journal" / f"{event['step_id']}.json"
    payload = json.loads(step_path.read_text(encoding="utf-8"))
    assert payload["shadow_manifest_path"].endswith("manifest.json")


def test_auto_journal_bash_mutation_records_side_effect_scope(tmp_path: Path) -> None:
    """Mutation-capable bash records side-effect scope from classify_side_effect."""
    from runtime.tool_plan_gate import journal_mutation_bash

    result = journal_mutation_bash(
        str(tmp_path),
        command="git commit -m 'fix'",
        run_id="bash-run-001",
    )

    assert result is not None
    assert result["status"] == "recorded"

    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    entries = list(journal_dir.glob("*.json"))
    assert len(entries) == 1

    payload = json.loads(entries[0].read_text(encoding="utf-8"))
    assert payload["tool"] == "bash"
    assert payload["metadata"]["run_id"] == "bash-run-001"
    assert "side_effect_scope" in payload
    assert payload["side_effect_scope"] == "git_commit"


def test_auto_journal_bash_destructive_records_irreversible(tmp_path: Path) -> None:
    """Destructive bash commands record irreversible side-effect scope."""
    from runtime.tool_plan_gate import journal_mutation_bash

    result = journal_mutation_bash(
        str(tmp_path),
        command="curl https://api.example.com/deploy",
        run_id="bash-run-002",
    )

    assert result is not None
    journal_dir = tmp_path / ".omg" / "state" / "interaction_journal"
    entries = list(journal_dir.glob("*.json"))
    payload = json.loads(entries[0].read_text(encoding="utf-8"))
    assert payload["side_effect_scope"] == "irreversible"


def test_read_only_operation_has_no_rollback_promise(tmp_path: Path) -> None:
    """Read-only tools must NOT get rollback promises."""
    journal = InteractionJournal(str(tmp_path))

    event = journal.record_step("read", {"file": "README.md"})

    assert event["rollback_mode"] == "unsupported"
    step_path = tmp_path / ".omg" / "state" / "interaction_journal" / f"{event['step_id']}.json"
    payload = json.loads(step_path.read_text(encoding="utf-8"))
    assert payload["shadow_manifest_path"] == ""
    assert "side_effect_scope" not in payload


def test_noop_glob_grep_excluded_from_rollback(tmp_path: Path) -> None:
    """Glob and Grep operations have unsupported rollback mode and no shadow."""
    journal = InteractionJournal(str(tmp_path))

    for tool in ("glob", "grep", "read"):
        event = journal.record_step(tool, {"pattern": "*.py"})
        assert event["rollback_mode"] == "unsupported", f"{tool} should have unsupported rollback"
        step_path = tmp_path / ".omg" / "state" / "interaction_journal" / f"{event['step_id']}.json"
        payload = json.loads(step_path.read_text(encoding="utf-8"))
        assert payload["shadow_manifest_path"] == "", f"{tool} should have empty shadow manifest"


def test_undo_bash_compensating_action_executes_and_records_result(tmp_path: Path) -> None:
    marker = tmp_path / "compensation.marker"
    command = f"python3 -c \"from pathlib import Path; Path({str(marker)!r}).write_text('done\\n', encoding='utf-8')\""
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step(
        "bash",
        {
            "command": "curl -X POST https://api.example.test/v1/resource",
            "run_id": "undo-run-001",
            "compensating_action": {
                "action": "mark compensation complete",
                "command": command,
            },
        },
    )

    result = journal.undo(cast(str, event["step_id"]))

    assert result["status"] == "ok"
    assert result["reason"] == "rollback complete"
    assert marker.read_text(encoding="utf-8") == "done\n"
    manifest_path = tmp_path / ".omg" / "state" / "rollback_manifest" / f"undo-run-001-{event['step_id']}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["compensating_actions"][0]["status"] == "succeeded"


def test_undo_restores_snapshot_state_before_compensation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMG_SNAPSHOT_ENABLED", "1")
    state_file = tmp_path / ".omg" / "state" / "session.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("v1\n", encoding="utf-8")
    marker = tmp_path / "snapshot_comp.marker"
    command = (
        "python3 -c \"from pathlib import Path; "
        f"Path({str(marker)!r}).write_text('after-snapshot', encoding='utf-8')\""
    )
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step(
        "write",
        {
            "file": "README.md",
            "run_id": "undo-run-002",
            "compensating_action": {
                "action": "write marker",
                "command": command,
            },
        },
    )
    state_file.write_text("v2\n", encoding="utf-8")

    result = journal.undo(cast(str, event["step_id"]))

    assert result["status"] == "ok"
    assert state_file.read_text(encoding="utf-8") == "v1\n"
    assert marker.read_text(encoding="utf-8") == "after-snapshot"
