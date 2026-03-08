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

    result = journal.undo(cast(str, event["step_id"]))

    assert result == {"status": "unsupported", "reason": "external side effect scope"}


def test_undo_write_attempts_shadow_restore_when_available(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "README.md"
    target.write_text("v1\n", encoding="utf-8")
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step("write", {"file": "README.md"})

    import hooks.shadow_manager as shadow_manager

    def _restore_shadow_entry(*args, **kwargs):
        return {"status": "ok", "args": args, "kwargs": kwargs}

    monkeypatch.setattr(shadow_manager, "restore_shadow_entry", _restore_shadow_entry, raising=False)
    result = journal.undo(cast(str, event["step_id"]))

    assert result["status"] == "ok"


def test_undo_latest_no_entries_is_noop(tmp_path: Path) -> None:
    journal = InteractionJournal(str(tmp_path))

    result = journal.undo("")

    assert result == {"status": "noop", "reason": "no journal entries"}
