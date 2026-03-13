from __future__ import annotations

import json
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
        scope=f"tool-fabric/{lane_name}",
        reason="approved for governed lane execution",
        signer_key_id=_DEV_KEY_ID,
        signer_private_key=_DEV_PRIVATE_KEY,
    )
    return {
        "artifact_digest": approval.artifact_digest,
        "action": approval.action,
        "scope": approval.scope,
        "reason": approval.reason,
        "signer_key_id": approval.signer_key_id,
        "issued_at": approval.issued_at,
        "signature": approval.signature,
    }


def test_approved_governed_tool_executes_through_canonical_fabric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-allow"
    _seed_tool_plan(tmp_path, run_id)
    evidence_path = tmp_path / ".omg" / "evidence" / "hash-edit.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("{}", encoding="utf-8")

    fabric = ToolFabric(project_dir=str(tmp_path))
    _register_lanes(fabric)

    result = fabric.request_tool(
        lane_name="hash-edit",
        tool_name="Edit",
        run_id=run_id,
        context={
            "approval_artifact": _approval_for("hash-edit", "Edit", run_id),
            "executor": lambda **_kwargs: {"status": "executed"},
        },
    )

    assert result.allowed is True
    assert result.reason == "allowed"
    assert result.evidence_path == ".omg/evidence/hash-edit.json"
    assert isinstance(result.ledger_entry, dict)
    assert result.ledger_entry.get("lane") == "hash-edit"


def test_unapproved_tool_request_is_blocked_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-deny"
    _seed_tool_plan(tmp_path, run_id)
    evidence_path = tmp_path / ".omg" / "evidence" / "hash-edit.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("{}", encoding="utf-8")

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


def test_missing_attestation_blocks_terminal_lane_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-attestation"
    _seed_tool_plan(tmp_path, run_id)
    evidence_path = tmp_path / ".omg" / "evidence" / f"terminal-lane-{run_id}.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("{}", encoding="utf-8")

    fabric = ToolFabric(project_dir=str(tmp_path))
    _register_lanes(fabric)

    result = fabric.request_tool(
        lane_name="terminal-lane",
        tool_name="Bash",
        run_id=run_id,
        context={
            "approval_artifact": _approval_for("terminal-lane", "Bash", run_id),
        },
    )

    assert result.allowed is False
    assert "missing attestation artifact" in result.reason
    assert result.ledger_entry is None


def test_tool_execution_is_recorded_in_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    run_id = "run-fabric-ledger"
    _seed_tool_plan(tmp_path, run_id)
    evidence_path = tmp_path / ".omg" / "evidence" / "hash-edit.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("{}", encoding="utf-8")

    fabric = ToolFabric(project_dir=str(tmp_path))
    _register_lanes(fabric)

    result = fabric.request_tool(
        lane_name="hash-edit",
        tool_name="Edit",
        run_id=run_id,
        context={
            "approval_artifact": _approval_for("hash-edit", "Edit", run_id),
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
