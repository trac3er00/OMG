from __future__ import annotations

from runtime.evidence_narrator import narrate
from runtime.verdict_schema import action_required_verdict, fail_verdict, pass_verdict


def test_narrate_pass():
    verdict = pass_verdict(evidence_paths={"logs": "path/to/logs"})
    result = narrate(verdict)
    
    assert "passed" in result["verdict_summary"].lower()
    assert result["blockers_section"] == []
    assert result["next_actions"] == []
    assert "logs" in str(result["evidence_paths_section"])


def test_narrate_fail():
    verdict = fail_verdict(["no_tests", "security_vulnerability"])
    result = narrate(verdict)
    
    assert "failed" in result["verdict_summary"].lower()
    assert "no_tests" in result["blockers_section"]
    assert "security_vulnerability" in result["blockers_section"]


def test_narrate_action_required():
    verdict = action_required_verdict(["missing_approval"], next_steps=["approve the PR"])
    result = narrate(verdict)
    
    assert "action required" in result["verdict_summary"].lower()
    assert "missing_approval" in result["blockers_section"]
    assert "approve the PR" in result["next_actions"]


def test_narrate_has_all_fields():
    verdict = pass_verdict()
    result = narrate(verdict)
    
    required_fields = {
        "verdict_summary",
        "blockers_section",
        "provenance_note",
        "evidence_paths_section",
        "next_actions",
    }
    assert set(result.keys()) == required_fields


def test_narrate_pending():
    verdict = action_required_verdict([])
    result = narrate(verdict)
    
    assert "pending" in result["verdict_summary"].lower() or "action" in result["verdict_summary"].lower()


def test_narrate_block_reason_known_code():
    from runtime.evidence_narrator import narrate_block_reason
    
    result = narrate_block_reason("no_active_test_intent_lock", {"tool": "Bash"})
    
    assert "test-intent lock" in result["verdict_summary"].lower()
    assert "no_active_test_intent_lock" in result["blockers_section"]
    assert len(result["next_actions"]) > 0
    assert any("omg_test_intent_lock" in action for action in result["next_actions"])


def test_narrate_block_reason_unknown_fallback():
    from runtime.evidence_narrator import narrate_block_reason
    
    result = narrate_block_reason("unknown_reason_code", {})
    
    assert result["verdict_summary"]
    assert "unknown_reason_code" in result["blockers_section"]
    assert len(result["next_actions"]) > 0


def test_format_block_explanation_contains_key_text():
    from runtime.evidence_narrator import format_block_explanation
    
    output = format_block_explanation("no_active_test_intent_lock", {"tool": "Bash"})
    
    assert "test-intent lock" in output.lower()
    assert "—" in output
    assert len(output) > 0
