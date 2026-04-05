"""Tests for hooks/approval_ui.py — terminal approval UI for governance gates."""

import json
from pathlib import Path

import pytest

from hooks.approval_ui import (
    _build_action_description,
    _check_preapproval,
    _format_approval_request,
    _sign_approval_record,
    log_approval_decision,
    present_approval_request,
    resolve_governance_ask,
)
from hooks.trust_review import review_config_change


class TestFormatApprovalRequest:
    def test_contains_action_and_risk(self):
        output = _format_approval_request(
            action="Add MCP server",
            risk_level="high",
            reasons=["New server added"],
            controls=["mcp-endpoint-review"],
        )
        assert "Add MCP server" in output
        assert "HIGH" in output

    def test_contains_reasons(self):
        output = _format_approval_request(
            action="test",
            risk_level="med",
            reasons=["Reason one", "Reason two"],
            controls=[],
        )
        assert "Reason one" in output
        assert "Reason two" in output

    def test_contains_controls(self):
        output = _format_approval_request(
            action="test",
            risk_level="low",
            reasons=[],
            controls=["ctrl-a", "ctrl-b"],
        )
        assert "ctrl-a" in output
        assert "ctrl-b" in output

    def test_contains_alternatives_when_provided(self):
        output = _format_approval_request(
            action="test",
            risk_level="low",
            reasons=[],
            controls=[],
            alternatives=["Use safer config", "Pin package version"],
        )
        assert "Use safer config" in output
        assert "Pin package version" in output

    def test_contains_option_labels(self):
        output = _format_approval_request(
            action="test",
            risk_level="low",
            reasons=[],
            controls=[],
        )
        assert "[a]" in output
        assert "[d]" in output
        assert "[A]" in output
        assert "[D]" in output

    def test_truncates_long_reasons(self):
        reasons = [f"Reason {i}" for i in range(20)]
        output = _format_approval_request(
            action="test",
            risk_level="low",
            reasons=reasons,
            controls=[],
        )
        assert "Reason 7" in output
        assert "Reason 8" not in output


class TestPresentApprovalRequest:
    def test_approve_via_input(self, tmp_path: Path):
        result = present_approval_request(
            action="Add MCP server",
            risk_level="high",
            reasons=["New server"],
            project_dir=str(tmp_path),
            _input_fn=lambda _: "a",
        )
        assert result == "approve"

    def test_deny_via_input(self, tmp_path: Path):
        result = present_approval_request(
            action="Risky change",
            risk_level="critical",
            reasons=["Dangerous"],
            project_dir=str(tmp_path),
            _input_fn=lambda _: "d",
        )
        assert result == "deny"

    def test_approve_all_via_uppercase_A(self, tmp_path: Path):
        result = present_approval_request(
            action="MCP modify",
            risk_level="med",
            project_dir=str(tmp_path),
            _input_fn=lambda _: "A",
        )
        assert result == "approve_all"

    def test_deny_all_via_uppercase_D(self, tmp_path: Path):
        result = present_approval_request(
            action="MCP modify",
            risk_level="med",
            project_dir=str(tmp_path),
            _input_fn=lambda _: "D",
        )
        assert result == "deny_all"

    def test_yes_maps_to_approve(self, tmp_path: Path):
        result = present_approval_request(
            action="test",
            risk_level="low",
            project_dir=str(tmp_path),
            _input_fn=lambda _: "yes",
        )
        assert result == "approve"

    def test_no_maps_to_deny(self, tmp_path: Path):
        result = present_approval_request(
            action="test",
            risk_level="low",
            project_dir=str(tmp_path),
            _input_fn=lambda _: "no",
        )
        assert result == "deny"

    def test_empty_input_defaults_to_deny(self, tmp_path: Path):
        result = present_approval_request(
            action="test",
            risk_level="low",
            project_dir=str(tmp_path),
            _input_fn=lambda _: "",
        )
        assert result == "deny"

    def test_eof_defaults_to_deny(self, tmp_path: Path):
        def raise_eof(_):
            raise EOFError

        result = present_approval_request(
            action="test",
            risk_level="low",
            project_dir=str(tmp_path),
            _input_fn=raise_eof,
        )
        assert result == "deny"

    def test_keyboard_interrupt_defaults_to_deny(self, tmp_path: Path):
        def raise_ki(_):
            raise KeyboardInterrupt

        result = present_approval_request(
            action="test",
            risk_level="low",
            project_dir=str(tmp_path),
            _input_fn=raise_ki,
        )
        assert result == "deny"


class TestPreApprovals:
    def test_allow_all_preapproval(self, tmp_path: Path):
        approvals_dir = tmp_path / ".omg" / "state"
        approvals_dir.mkdir(parents=True)
        (approvals_dir / "ralph-approvals.json").write_text(
            json.dumps({"allow_all": True})
        )
        result = present_approval_request(
            action="anything",
            risk_level="critical",
            project_dir=str(tmp_path),
        )
        assert result == "approve"

    def test_risk_level_preapproval(self, tmp_path: Path):
        approvals_dir = tmp_path / ".omg" / "state"
        approvals_dir.mkdir(parents=True)
        (approvals_dir / "ralph-approvals.json").write_text(
            json.dumps({"approved_risk_levels": ["med", "low"]})
        )
        result = present_approval_request(
            action="safe change",
            risk_level="med",
            project_dir=str(tmp_path),
        )
        assert result == "approve"

    def test_risk_level_not_preapproved_falls_through(self, tmp_path: Path):
        approvals_dir = tmp_path / ".omg" / "state"
        approvals_dir.mkdir(parents=True)
        (approvals_dir / "ralph-approvals.json").write_text(
            json.dumps({"approved_risk_levels": ["low"]})
        )
        result = present_approval_request(
            action="high risk",
            risk_level="high",
            project_dir=str(tmp_path),
            _input_fn=lambda _: "d",
        )
        assert result == "deny"

    def test_action_specific_preapproval(self, tmp_path: Path):
        approvals_dir = tmp_path / ".omg" / "state"
        approvals_dir.mkdir(parents=True)
        (approvals_dir / "ralph-approvals.json").write_text(
            json.dumps({"approved_actions": ["Add MCP server: foo"]})
        )
        result = present_approval_request(
            action="Add MCP server: foo",
            risk_level="high",
            project_dir=str(tmp_path),
        )
        assert result == "approve"

    def test_no_preapproval_file_falls_through(self, tmp_path: Path):
        result = present_approval_request(
            action="test",
            risk_level="low",
            project_dir=str(tmp_path),
            _input_fn=lambda _: "a",
        )
        assert result == "approve"


class TestLogApprovalDecision:
    def test_creates_ledger_file(self, tmp_path: Path):
        log_approval_decision(
            project_dir=str(tmp_path),
            action="test action",
            decision="approve",
            risk_level="low",
            mode="cli_interactive",
        )
        ledger = tmp_path / ".omg" / "state" / "ledger" / "approvals.jsonl"
        assert ledger.exists()
        records = [json.loads(line) for line in ledger.read_text().strip().split("\n")]
        assert len(records) == 1
        assert records[0]["action"] == "test action"
        assert records[0]["decision"] == "approve"
        assert records[0]["risk_level"] == "low"
        assert records[0]["mode"] == "cli_interactive"
        assert "digest" in records[0]
        assert "ts" in records[0]

    def test_appends_multiple_records(self, tmp_path: Path):
        for i in range(3):
            log_approval_decision(
                project_dir=str(tmp_path),
                action=f"action-{i}",
                decision="deny",
                risk_level="high",
                mode="auto_deny",
            )
        ledger = tmp_path / ".omg" / "state" / "ledger" / "approvals.jsonl"
        records = [json.loads(line) for line in ledger.read_text().strip().split("\n")]
        assert len(records) == 3
        assert records[2]["action"] == "action-2"

    def test_digest_is_valid_sha256(self, tmp_path: Path):
        log_approval_decision(
            project_dir=str(tmp_path),
            action="verify digest",
            decision="approve",
            risk_level="low",
            mode="test",
        )
        ledger = tmp_path / ".omg" / "state" / "ledger" / "approvals.jsonl"
        record = json.loads(ledger.read_text().strip())
        digest = record.pop("digest")
        assert len(digest) == 64
        recomputed = _sign_approval_record(record)
        assert recomputed == digest


class TestResolveGovernanceAsk:
    def test_allow_verdict_passes_through(self, tmp_path: Path):
        review = {"verdict": "allow", "risk_level": "low"}
        result = resolve_governance_ask(review, project_dir=str(tmp_path))
        assert result["verdict"] == "allow"
        assert "approval_resolution" not in result

    def test_deny_verdict_passes_through(self, tmp_path: Path):
        review = {"verdict": "deny", "risk_level": "critical"}
        result = resolve_governance_ask(review, project_dir=str(tmp_path))
        assert result["verdict"] == "deny"
        assert "approval_resolution" not in result

    def test_ask_resolved_to_allow_on_approve(self, tmp_path: Path):
        review = {
            "verdict": "ask",
            "risk_level": "med",
            "reasons": ["Hook modified"],
            "controls": ["hook-diff-review"],
            "changed_files": ["settings.json"],
            "mcp_changes": [],
            "hook_changes": {},
            "env_changes": [],
        }
        result = resolve_governance_ask(
            review, project_dir=str(tmp_path), _input_fn=lambda _: "a"
        )
        assert result["verdict"] == "allow"
        assert result["approval_resolution"]["original_verdict"] == "ask"
        assert result["approval_resolution"]["user_decision"] == "approve"
        assert result["approval_resolution"]["resolved_verdict"] == "allow"

    def test_ask_resolved_to_deny_on_deny(self, tmp_path: Path):
        review = {
            "verdict": "ask",
            "risk_level": "high",
            "reasons": ["Dangerous"],
            "controls": ["manual-review"],
            "changed_files": [],
            "mcp_changes": [],
            "hook_changes": {},
            "env_changes": [],
        }
        result = resolve_governance_ask(
            review, project_dir=str(tmp_path), _input_fn=lambda _: "d"
        )
        assert result["verdict"] == "deny"
        assert result["approval_resolution"]["user_decision"] == "deny"


class TestBuildActionDescription:
    def test_from_changed_files(self):
        review = {
            "changed_files": ["settings.json"],
            "mcp_changes": [],
            "hook_changes": {},
            "env_changes": [],
        }
        desc = _build_action_description(review)
        assert "settings.json" in desc

    def test_from_mcp_changes(self):
        review = {
            "changed_files": [],
            "mcp_changes": [{"type": "added", "server": "filesystem"}],
            "hook_changes": {},
            "env_changes": [],
        }
        desc = _build_action_description(review)
        assert "MCP server added: filesystem" in desc

    def test_from_env_changes(self):
        review = {
            "changed_files": [],
            "mcp_changes": [],
            "hook_changes": {},
            "env_changes": [{"key": "API_KEY"}],
        }
        desc = _build_action_description(review)
        assert "API_KEY" in desc

    def test_fallback_to_reasons(self):
        review = {
            "changed_files": [],
            "mcp_changes": [],
            "hook_changes": {},
            "env_changes": [],
            "reasons": ["Something happened"],
        }
        desc = _build_action_description(review)
        assert "Something happened" in desc

    def test_fallback_to_generic(self):
        review = {
            "changed_files": [],
            "mcp_changes": [],
            "hook_changes": {},
            "env_changes": [],
        }
        desc = _build_action_description(review)
        assert "Configuration change requiring approval" in desc


class TestReviewConfigChangeWithResolveAsk:
    def test_ask_verdict_resolved_when_flag_set(self, tmp_path: Path):
        old = {"mcpServers": {}}
        new = {"mcpServers": {"new-server": {"command": "npx", "args": ["-y", "pkg"]}}}
        review = review_config_change(
            ".mcp.json",
            old,
            new,
            resolve_ask=True,
            project_dir=str(tmp_path),
            _input_fn=lambda _: "a",
        )
        assert review["verdict"] == "allow"
        assert "approval_resolution" in review

    def test_ask_not_resolved_when_flag_unset(self):
        old = {"mcpServers": {}}
        new = {"mcpServers": {"new-server": {"command": "npx", "args": ["-y", "pkg"]}}}
        review = review_config_change(".mcp.json", old, new)
        assert review["verdict"] == "ask"
        assert "approval_resolution" not in review

    def test_deny_verdict_not_affected_by_resolve_flag(self, tmp_path: Path):
        old = {"permissions": {"allow": ["Read"]}}
        new = {"permissions": {"allow": ["Read", "Bash(sudo:*)"]}}
        review = review_config_change(
            "settings.json",
            old,
            new,
            resolve_ask=True,
            project_dir=str(tmp_path),
        )
        assert review["verdict"] == "deny"
        assert "approval_resolution" not in review

    def test_interactive_approval_creates_ledger_entry(self, tmp_path: Path):
        old = {"mcpServers": {}}
        new = {"mcpServers": {"test-srv": {"command": "npx", "args": ["-y", "pkg"]}}}
        review_config_change(
            ".mcp.json",
            old,
            new,
            resolve_ask=True,
            project_dir=str(tmp_path),
            _input_fn=lambda _: "a",
        )
        ledger = tmp_path / ".omg" / "state" / "ledger" / "approvals.jsonl"
        assert ledger.exists()
        record = json.loads(ledger.read_text().strip().split("\n")[-1])
        assert record["decision"] == "approve"
        assert record["risk_level"] in ("med", "high")
