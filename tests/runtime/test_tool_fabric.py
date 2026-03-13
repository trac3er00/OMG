from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from registry.approval_artifact import build_tool_approval_digest, create_approval_artifact
from runtime.tool_fabric import ToolFabric


_DEV_PRIVATE_KEY = "Hx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8="
_DEV_KEY_ID = "1f5fe64ec2f8c901"


def _seed_tool_plan(tmp_path: Path, run_id: str) -> None:
    plans_dir = tmp_path / ".omg" / "state" / "tool_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{run_id}-plan-test.json").write_text("{}", encoding="utf-8")


def _register_lanes(fabric: ToolFabric) -> None:
    fabric.register_lane("lsp-pack", "registry/bundles/lsp-pack.yaml")
    fabric.register_lane("hash-edit", "registry/bundles/hash-edit.yaml")
    fabric.register_lane("ast-pack", "registry/bundles/ast-pack.yaml")
    fabric.register_lane("terminal-lane", "registry/bundles/terminal-lane.yaml")


def _approval_for(lane_name: str, tool_name: str, run_id: str) -> dict[str, object]:
    digest = build_tool_approval_digest(lane_name=lane_name, tool_name=tool_name, run_id=run_id)
    approval = create_approval_artifact(
        artifact_digest=digest,
        action="allow",
        scope=f"tool-fabric/{lane_name}/runs/{run_id}",
        reason="approved for governed lane execution",
        signer_key_id=_DEV_KEY_ID,
        signer_private_key=_DEV_PRIVATE_KEY,
        run_id=run_id,
    )
    payload: dict[str, object] = {
        "artifact_digest": approval.artifact_digest,
        "action": approval.action,
        "scope": approval.scope,
        "reason": approval.reason,
        "signer_key_id": approval.signer_key_id,
        "issued_at": approval.issued_at,
        "signature": approval.signature,
    }
    if approval.run_id:
        payload["run_id"] = approval.run_id
    return payload


def _seed_lane_evidence(
    tmp_path: Path,
    lane_name: str,
    run_id: str,
    tool_name: str,
    *,
    stale: bool = False,
) -> None:
    evidence_path = tmp_path / ".omg" / "evidence" / f"{lane_name}-{run_id}.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_run_id = f"{run_id}-stale" if stale else run_id
    payload = {
        "run_id": evidence_run_id,
        "lane": lane_name,
        "tool": tool_name,
        "generated_at": (
            datetime.now(timezone.utc) - timedelta(days=2) if stale else datetime.now(timezone.utc)
        ).isoformat(),
    }
    evidence_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def test_approved_governed_lane_executes_with_fresh_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-allow"
    _seed_tool_plan(tmp_path, run_id)
    _seed_lane_evidence(tmp_path, "hash-edit", run_id, "Edit")

    fabric = ToolFabric(project_dir=str(tmp_path))
    _register_lanes(fabric)

    result = fabric.request_tool(
        lane_name="hash-edit",
        tool_name="Edit",
        run_id=run_id,
        context={
            "approval_artifact": _approval_for("hash-edit", "Edit", run_id),
            "operation": "single_file_hash_edit",
            "target_file": "runtime/tool_fabric.py",
            "expected_hash": "a" * 64,
            "attestation_artifact": {
                "run_id": run_id,
                "lane": "hash-edit",
                "tool": "Edit",
                "attested_at": datetime.now(timezone.utc).isoformat(),
            },
            "executor": lambda **_kwargs: {"status": "executed"},
        },
    )

    assert result.allowed is True
    assert result.reason == "allowed"
    assert result.evidence_path == f".omg/evidence/hash-edit-{run_id}.json"
    assert isinstance(result.ledger_entry, dict)
    assert result.ledger_entry.get("lane") == "hash-edit"


def test_unapproved_tool_request_is_blocked_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-deny"
    _seed_tool_plan(tmp_path, run_id)
    _seed_lane_evidence(tmp_path, "hash-edit", run_id, "Edit")

    fabric = ToolFabric(project_dir=str(tmp_path))
    _register_lanes(fabric)

    result = fabric.request_tool(
        lane_name="hash-edit",
        tool_name="Edit",
        run_id=run_id,
        context={},
    )

    assert result.allowed is False
    assert "signed approval required" in result.reason
    assert result.ledger_entry is None


def test_missing_attestation_or_stale_evidence_blocks_mutation_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-guardrails"
    _seed_tool_plan(tmp_path, run_id)
    _seed_lane_evidence(tmp_path, "hash-edit", run_id, "Edit")

    fabric = ToolFabric(project_dir=str(tmp_path))
    _register_lanes(fabric)

    result = fabric.request_tool(
        lane_name="hash-edit",
        tool_name="Edit",
        run_id=run_id,
        context={
            "approval_artifact": _approval_for("hash-edit", "Edit", run_id),
            "operation": "single_file_hash_edit",
            "target_file": "runtime/tool_fabric.py",
            "expected_hash": "a" * 64,
        },
    )

    assert result.allowed is False
    assert "missing attestation artifact" in result.reason
    assert result.ledger_entry is None

    stale_run_id = "run-fabric-stale"
    _seed_tool_plan(tmp_path, stale_run_id)
    _seed_lane_evidence(tmp_path, "hash-edit", stale_run_id, "Edit", stale=True)

    stale_result = fabric.request_tool(
        lane_name="hash-edit",
        tool_name="Edit",
        run_id=stale_run_id,
        context={
            "approval_artifact": _approval_for("hash-edit", "Edit", stale_run_id),
            "operation": "single_file_hash_edit",
            "target_file": "runtime/tool_fabric.py",
            "expected_hash": "a" * 64,
            "attestation_artifact": {
                "run_id": stale_run_id,
                "lane": "hash-edit",
                "tool": "Edit",
                "attested_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )

    assert stale_result.allowed is False
    assert "evidence run_id mismatch" in stale_result.reason
    assert stale_result.ledger_entry is None


def test_tool_execution_is_recorded_in_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-ledger"
    _seed_tool_plan(tmp_path, run_id)
    _seed_lane_evidence(tmp_path, "hash-edit", run_id, "Edit")

    fabric = ToolFabric(project_dir=str(tmp_path))
    _register_lanes(fabric)

    result = fabric.request_tool(
        lane_name="hash-edit",
        tool_name="Edit",
        run_id=run_id,
        context={
            "approval_artifact": _approval_for("hash-edit", "Edit", run_id),
            "operation": "single_file_hash_edit",
            "target_file": "runtime/tool_fabric.py",
            "expected_hash": "a" * 64,
            "attestation_artifact": {
                "run_id": run_id,
                "lane": "hash-edit",
                "tool": "Edit",
                "attested_at": datetime.now(timezone.utc).isoformat(),
            },
            "executor": lambda **_kwargs: {"status": "ok", "changed": 1},
        },
    )

    assert result.allowed is True

    ledger_path = tmp_path / ".omg" / "state" / "ledger" / "tool-ledger.jsonl"
    assert ledger_path.exists()
    lines = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    last = json.loads(lines[-1])
    assert last["source"] == "tool-fabric"
    assert last["lane"] == "hash-edit"
    assert last["run_id"] == run_id
