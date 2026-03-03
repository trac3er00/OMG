"""Tests for legacy -> .omg migration helpers."""
from __future__ import annotations

import json
from pathlib import Path

from hooks.state_migration import migrate_legacy_to_omg, resolve_state_file


def test_migrate_legacy_to_omg_copies_canonical_paths(tmp_path: Path):
    legacy = tmp_path / ".omc"
    (legacy / "ledger").mkdir(parents=True)
    (legacy / "knowledge").mkdir(parents=True)

    (legacy / "profile.yaml").write_text("name: demo\n", encoding="utf-8")
    (legacy / "working-memory.md").write_text("remember this\n", encoding="utf-8")
    (legacy / "_plan.md").write_text("CHANGE_BUDGET=small\n", encoding="utf-8")
    (legacy / "_checklist.md").write_text("- [ ] one\n", encoding="utf-8")
    (legacy / "handoff.md").write_text("# handoff\n", encoding="utf-8")
    (legacy / "handoff-portable.md").write_text("# handoff portable\n", encoding="utf-8")
    (legacy / "ledger" / "tool-ledger.jsonl").write_text("", encoding="utf-8")
    (legacy / "knowledge" / "note.md").write_text("k", encoding="utf-8")

    report = migrate_legacy_to_omg(str(tmp_path))
    assert report["result"] == "ok"

    assert (tmp_path / ".omg" / "state" / "profile.yaml").exists()
    assert (tmp_path / ".omg" / "state" / "working-memory.md").exists()
    assert (tmp_path / ".omg" / "state" / "_plan.md").exists()
    assert (tmp_path / ".omg" / "state" / "_checklist.md").exists()
    assert (tmp_path / ".omg" / "state" / "handoff.md").exists()
    assert (tmp_path / ".omg" / "state" / "handoff-portable.md").exists()
    assert (tmp_path / ".omg" / "state" / "ledger" / "tool-ledger.jsonl").exists()
    assert (tmp_path / ".omg" / "knowledge" / "note.md").exists()

    migration_log = tmp_path / ".omg" / "migrations" / "legacy-to-omg.json"
    assert migration_log.exists()
    payload = json.loads(migration_log.read_text(encoding="utf-8"))
    assert (tmp_path / ".omg" / "migrations" / "omc-to-omg.json").exists()
    assert payload["legacy_path"].endswith(".omc")


def test_resolve_state_file_prefers_omg_and_is_idempotent(tmp_path: Path):
    legacy = tmp_path / ".omc"
    legacy.mkdir(parents=True)
    (legacy / "profile.yaml").write_text("name: from-legacy\n", encoding="utf-8")

    first = resolve_state_file(str(tmp_path), "state/profile.yaml", "profile.yaml")
    second = resolve_state_file(str(tmp_path), "state/profile.yaml", "profile.yaml")

    assert first.endswith(".omg/state/profile.yaml")
    assert second.endswith(".omg/state/profile.yaml")
    assert (tmp_path / ".omg" / "state" / "profile.yaml").read_text(encoding="utf-8") == "name: from-legacy\n"


def test_migrate_legacy_to_omg_copies_runtime_state_for_hud_and_router(tmp_path: Path):
    legacy = tmp_path / ".omc"
    (legacy / "state" / "checkpoints").mkdir(parents=True)
    (legacy / "sessions").mkdir(parents=True)
    (legacy / "snapshots" / "20260227_171455").mkdir(parents=True)

    (legacy / "state" / "hud-stdin-cache.json").write_text("{}", encoding="utf-8")
    (legacy / "state" / "team-state.json").write_text('{"target":"gemini"}\n', encoding="utf-8")
    (legacy / "state" / "subagent-tracking.json").write_text(
        '{"agents":[{"agent_type":"codex"}]}\n',
        encoding="utf-8",
    )
    (legacy / "state" / "checkpoints" / "checkpoint-1.json").write_text("{}", encoding="utf-8")
    (legacy / "sessions" / "session-1.json").write_text('{"mode":"codex"}\n', encoding="utf-8")
    (legacy / "snapshots" / "20260227_171455" / "tool-ledger.jsonl").write_text("", encoding="utf-8")

    report = migrate_legacy_to_omg(str(tmp_path))
    assert report["result"] == "ok"

    assert (tmp_path / ".omg" / "state" / "hud-stdin-cache.json").exists()
    assert (tmp_path / ".omg" / "state" / "team-state.json").exists()
    assert (tmp_path / ".omg" / "state" / "subagent-tracking.json").exists()
    assert (tmp_path / ".omg" / "state" / "checkpoints" / "checkpoint-1.json").exists()
    assert (tmp_path / ".omg" / "state" / "sessions" / "session-1.json").exists()
    assert (tmp_path / ".omg" / "state" / "snapshots" / "20260227_171455" / "tool-ledger.jsonl").exists()


def test_migrate_legacy_to_omg_copies_root_level_legacy_mode_state(tmp_path: Path):
    legacy = tmp_path / ".omc"
    legacy.mkdir(parents=True)

    (legacy / "autopilot-state.json").write_text('{"active":true}\n', encoding="utf-8")
    (legacy / "team-state.json").write_text('{"target":"codex"}\n', encoding="utf-8")
    (legacy / "hud-state.json").write_text('{"mode":"compact"}\n', encoding="utf-8")

    report = migrate_legacy_to_omg(str(tmp_path))
    assert report["result"] == "ok"

    assert (tmp_path / ".omg" / "state" / "autopilot-state.json").exists()
    assert (tmp_path / ".omg" / "state" / "team-state.json").exists()
    assert (tmp_path / ".omg" / "state" / "hud-state.json").exists()
