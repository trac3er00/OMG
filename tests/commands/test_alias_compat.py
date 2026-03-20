"""Tests for command alias compatibility in standalone mode."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# --- Parametrized existence + content checks ---


@pytest.mark.parametrize(
    "cmd_path,expected_keyword",
    [
        ("commands/OMG:teams.md", "teams"),
        ("commands/OMG:ccg.md", "ccg"),
        ("commands/OMG:browser.md", "browser"),
        ("commands/OMG:playwright.md", "alias"),
        ("commands/OMG:escalate.md", "escalate"),
        ("commands/OMG:deep-plan.md", "deep-plan"),
    ],
    ids=["teams", "ccg", "browser", "playwright", "escalate", "deep-plan"],
)
def test_command_file_exists_and_contains_keyword(cmd_path: str, expected_keyword: str) -> None:
    full = ROOT / cmd_path
    assert full.exists(), f"{cmd_path} must exist"
    content = full.read_text(encoding="utf-8")
    assert expected_keyword in content.lower(), f"{cmd_path} must mention '{expected_keyword}'"


# --- Legacy alias removal ---


@pytest.mark.parametrize(
    "legacy_path",
    ["commands/omg-teams.md", "commands/ccg.md"],
    ids=["omg-teams", "ccg-bare"],
)
def test_legacy_compat_aliases_removed(legacy_path: str) -> None:
    """Legacy aliases were removed in v1.0.3 — replaced by OMG: prefixed commands."""
    assert not (ROOT / legacy_path).exists(), f"{legacy_path} should be removed"


# --- Structural contract tests ---


def test_escalate_uses_internal_router_not_external_omc():
    escalate_doc = _read("commands/OMG:escalate.md")
    assert "~/.claude/omg-runtime/scripts/omg.py" in escalate_doc
    assert 'python3 "$OMG_CLI" teams' in escalate_doc
    assert 'python3 "$OMG_CLI" ccg' in escalate_doc
    assert "No external legacy plugin is required." in escalate_doc


def test_playwright_is_alias_for_browser():
    playwright_doc = _read("commands/OMG:playwright.md")
    assert "/OMG:browser" in playwright_doc, "playwright must reference browser as alias target"


def test_deep_plan_is_5_track_planning_command():
    deep_plan_doc = _read("commands/OMG:deep-plan.md")
    assert "/OMG:deep-plan" in deep_plan_doc
    # v2.2.12: deep-plan upgraded from plan-council stub to 5-track parallel planning
    assert "architect" in deep_plan_doc.lower() or "plan-council" in deep_plan_doc


# --- Error / edge case tests ---


def test_command_files_are_not_empty() -> None:
    """All command markdown files must have real content, not empty stubs."""
    cmd_dir = ROOT / "commands"
    for md in sorted(cmd_dir.glob("OMG:*.md")):
        content = md.read_text(encoding="utf-8").strip()
        assert len(content) > 50, f"{md.name} looks like an empty stub ({len(content)} chars)"


def test_command_files_have_no_circular_symlinks() -> None:
    """Regression: a previous bug created self-referencing symlinks like OMG:ccg.md -> OMG:ccg.md."""
    cmd_dir = ROOT / "commands"
    for md in sorted(cmd_dir.glob("OMG:*.md")):
        if md.is_symlink():
            target = md.resolve()
            assert target != md, f"{md.name} is a circular symlink"
            assert target.exists(), f"{md.name} symlink target {target} does not exist"


def test_no_command_references_deleted_workflows() -> None:
    """No command file should reference workflows that were deleted."""
    deleted_workflows = ["omg-compat-gate.yml", "omg-release-readiness.yml", "evidence-gate.yml"]
    cmd_dir = ROOT / "commands"
    for md in sorted(cmd_dir.glob("OMG:*.md")):
        content = md.read_text(encoding="utf-8")
        for wf in deleted_workflows:
            assert wf not in content, f"{md.name} references deleted workflow {wf}"
