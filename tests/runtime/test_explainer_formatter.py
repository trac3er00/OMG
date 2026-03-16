from __future__ import annotations

from typing import Any

from runtime.explainer_formatter import format_markdown, format_terminal


FULL_NARRATIVE: dict[str, Any] = {
    "verdict_summary": "The verification process passed successfully.",
    "blockers_section": ["missing_tests", "no_security_scan"],
    "provenance_note": "Evidence collected from CI pipeline run #42",
    "evidence_paths_section": ["tests: path/to/test-results.json", "scan: path/to/scan.json"],
    "next_actions": ["Run security scan", "Add integration tests"],
}

EMPTY_NARRATIVE: dict[str, Any] = {
    "verdict_summary": "All clear.",
    "blockers_section": [],
    "provenance_note": None,
    "evidence_paths_section": [],
    "next_actions": [],
}


def test_format_terminal_contains_verdict_summary():
    output = format_terminal(FULL_NARRATIVE)
    assert FULL_NARRATIVE["verdict_summary"] in output


def test_format_terminal_contains_next_actions():
    output = format_terminal(FULL_NARRATIVE)
    for action in FULL_NARRATIVE["next_actions"]:
        assert action in output


def test_format_terminal_contains_blockers():
    output = format_terminal(FULL_NARRATIVE)
    for blocker in FULL_NARRATIVE["blockers_section"]:
        assert blocker in output


def test_format_terminal_contains_evidence():
    output = format_terminal(FULL_NARRATIVE)
    for path in FULL_NARRATIVE["evidence_paths_section"]:
        assert path in output


def test_format_terminal_no_ansi():
    output = format_terminal(FULL_NARRATIVE)
    assert "\033[" not in output
    assert "\x1b[" not in output


def test_format_terminal_deterministic():
    a = format_terminal(FULL_NARRATIVE)
    b = format_terminal(FULL_NARRATIVE)
    assert a == b


def test_format_terminal_empty_narrative():
    output = format_terminal(EMPTY_NARRATIVE)
    assert "All clear." in output
    assert isinstance(output, str)
    assert len(output) > 0


def test_format_markdown_starts_with_h2():
    output = format_markdown(FULL_NARRATIVE)
    assert output.startswith("## ")


def test_format_markdown_contains_summary():
    output = format_markdown(FULL_NARRATIVE)
    assert FULL_NARRATIVE["verdict_summary"] in output


def test_format_markdown_contains_blockers_heading():
    output = format_markdown(FULL_NARRATIVE)
    assert "### Blockers" in output


def test_format_markdown_contains_next_actions_heading():
    output = format_markdown(FULL_NARRATIVE)
    assert "### Next Actions" in output


def test_format_markdown_contains_bullet_items():
    output = format_markdown(FULL_NARRATIVE)
    for blocker in FULL_NARRATIVE["blockers_section"]:
        assert f"- {blocker}" in output


def test_format_markdown_deterministic():
    a = format_markdown(FULL_NARRATIVE)
    b = format_markdown(FULL_NARRATIVE)
    assert a == b


def test_format_markdown_empty_narrative():
    output = format_markdown(EMPTY_NARRATIVE)
    assert output.startswith("## ")
    assert "All clear." in output
    assert isinstance(output, str)
    assert len(output) > 0


def test_terminal_and_markdown_differ():
    t = format_terminal(FULL_NARRATIVE)
    m = format_markdown(FULL_NARRATIVE)
    assert t != m


def test_both_formats_include_verdict():
    t = format_terminal(FULL_NARRATIVE)
    m = format_markdown(FULL_NARRATIVE)
    assert FULL_NARRATIVE["verdict_summary"] in t
    assert FULL_NARRATIVE["verdict_summary"] in m
