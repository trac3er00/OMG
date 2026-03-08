from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from runtime.interaction_journal import InteractionJournal
from runtime.rollback_manifest import (
    classify_side_effect,
    create_rollback_manifest,
    record_compensating_action,
    record_local_restore,
)


def test_create_manifest_records_schema_and_identity() -> None:
    manifest = create_rollback_manifest(run_id="run-1", step_id="step-1")

    assert manifest["schema"] == "RollbackManifest"
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["run_id"] == "run-1"
    assert manifest["step_id"] == "step-1"
    assert manifest["local_restores"] == []
    assert manifest["compensating_actions"] == []


def test_manifest_records_local_restore_and_compensating_action() -> None:
    manifest = create_rollback_manifest(run_id="run-2", step_id="step-2")
    record_local_restore(manifest, file_path="README.md", status="restored")
    record_compensating_action(
        manifest,
        effect_type="network_request",
        action="DELETE /v1/resource/123",
        command="curl -X DELETE https://api.example.test/v1/resource/123",
    )

    assert manifest["local_restores"][0]["file_path"] == "README.md"
    assert manifest["local_restores"][0]["status"] == "restored"
    assert manifest["compensating_actions"][0]["effect_type"] == "network_request"
    assert manifest["compensating_actions"][0]["command"].startswith("curl -X DELETE")


def test_classify_network_request_requires_compensation() -> None:
    reversible = classify_side_effect(
        tool="bash",
        metadata={
            "command": "curl -X POST https://api.example.test/v1/resource",
            "compensating_action": {
                "action": "DELETE /v1/resource/123",
                "command": "curl -X DELETE https://api.example.test/v1/resource/123",
            },
        },
    )
    irreversible = classify_side_effect(
        tool="bash",
        metadata={"command": "curl -X POST https://api.example.test/v1/resource"},
    )

    assert reversible["category"] == "network_request"
    assert reversible["decision"] == "reversible"
    assert reversible["reversible"] is True
    assert irreversible["category"] == "irreversible"
    assert irreversible["decision"] == "escalation_required"
    assert irreversible["reversible"] is False


def test_classify_irreversible_side_effects() -> None:
    git_commit = classify_side_effect(tool="bash", metadata={"command": "git commit -m 'msg'"})
    destructive = classify_side_effect(tool="bash", metadata={"command": "rm -rf /"})

    assert git_commit["category"] == "git_commit"
    assert git_commit["decision"] == "reversible"
    assert git_commit["reversible"] is True
    assert destructive["category"] == "irreversible"
    assert destructive["decision"] == "blocked"
    assert destructive["reversible"] is False


def test_undo_manifest_contains_local_and_compensating_outcomes(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("before\n", encoding="utf-8")
    marker = tmp_path / "manifest.marker"
    command = f"python3 -c \"from pathlib import Path; Path({str(marker)!r}).write_text('ok', encoding='utf-8')\""
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step(
        "write",
        {
            "file": "README.md",
            "run_id": "rollback-run-1",
            "compensating_action": {
                "action": "create marker",
                "command": command,
            },
        },
    )
    target.write_text("after\n", encoding="utf-8")

    result = journal.undo(cast(str, event["step_id"]))

    assert result["status"] == "ok"
    manifest_path = tmp_path / ".omg" / "state" / "rollback_manifest" / f"rollback-run-1-{event['step_id']}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["local_restores"]
    assert manifest["local_restores"][0]["status"] == "restored"
    assert manifest["compensating_actions"]
    assert manifest["compensating_actions"][0]["status"] == "succeeded"


def test_undo_manifest_failed_compensating_action_is_deterministic(tmp_path: Path) -> None:
    journal = InteractionJournal(str(tmp_path))
    event = journal.record_step(
        "bash",
        {
            "command": "curl -X POST https://api.example.test/v1/resource",
            "run_id": "rollback-run-failed",
            "compensating_action": {
                "action": "fail deterministically",
                "command": "python3 -c \"raise SystemExit(7)\"",
            },
        },
    )

    result = journal.undo(cast(str, event["step_id"]))

    result_obj = cast(dict[str, object], result)
    failed_actions = cast(list[dict[str, object]], result_obj["failed_actions"])
    assert result_obj["status"] == "rollback_failed"
    assert failed_actions
    assert failed_actions[0]["exit_code"] == 7
    manifest_path = tmp_path / ".omg" / "state" / "rollback_manifest" / f"rollback-run-failed-{event['step_id']}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["compensating_actions"][0]["status"] == "failed"
