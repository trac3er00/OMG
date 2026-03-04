"""Tests for command alias compatibility in standalone mode."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_legacy_compat_aliases_removed():
    """omg-teams.md and ccg.md compat aliases were removed in v1.0.3 — replaced by OMG:teams and OMG:ccg."""
    assert not (ROOT / "commands" / "omg-teams.md").exists()
    assert not (ROOT / "commands" / "ccg.md").exists()


def test_omg_teams_exists():
    teams_doc = _read("commands/OMG:teams.md")
    assert "teams" in teams_doc.lower()


def test_omg_ccg_exists():
    ccg_doc = _read("commands/OMG:ccg.md")
    assert "ccg" in ccg_doc.lower()


def test_escalate_uses_internal_router_not_external_omc():
    escalate_doc = _read("commands/OMG:escalate.md")
    assert "~/.claude/omg-runtime/scripts/omg.py" in escalate_doc
    assert "python3 \"$OMG_CLI\" teams" in escalate_doc
    assert "python3 \"$OMG_CLI\" ccg" in escalate_doc
    assert "No external legacy plugin is required." in escalate_doc
