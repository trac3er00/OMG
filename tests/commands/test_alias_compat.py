"""Tests for legacy command alias compatibility in standalone mode."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_legacy_omc_teams_alias_routes_to_omg():
    alias_doc = _read("commands/omc-teams.md")
    assert "/OMG:teams" in alias_doc
    assert "Compatibility alias" in alias_doc


def test_legacy_ccg_alias_routes_to_omg():
    alias_doc = _read("commands/ccg.md")
    assert "/OMG:ccg" in alias_doc
    assert "Compatibility alias" in alias_doc


def test_escalate_uses_internal_router_not_external_omc():
    escalate_doc = _read("commands/OMG:escalate.md")
    assert "~/.claude/omg-runtime/scripts/omg.py" in escalate_doc
    assert "python3 \"$OMG_CLI\" teams" in escalate_doc
    assert "python3 \"$OMG_CLI\" ccg" in escalate_doc
    assert "No external OMC plugin is required." in escalate_doc
