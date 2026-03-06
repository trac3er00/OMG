"""Tests for current provider CLI contracts used by OMG."""
from __future__ import annotations

from runtime import team_router


def test_codex_contract_matches_current_cli_shape():
    contract = team_router.get_cli_contract("codex")

    assert contract is not None
    assert contract["binary"] == "codex"
    assert contract["auth_probe_kind"] == "none"
    assert contract["auth_probe"] is None

    cmd = team_router.build_non_interactive_command("codex", "Reply with OK.", "/tmp/project")
    assert cmd == ["codex", "exec", "--json", "Reply with OK."]


def test_gemini_contract_matches_current_cli_shape():
    contract = team_router.get_cli_contract("gemini")

    assert contract is not None
    assert contract["binary"] == "gemini"
    assert contract["auth_probe_kind"] == "none"
    assert contract["auth_probe"] is None

    cmd = team_router.build_non_interactive_command("gemini", "Reply with OK.", "/tmp/project")
    assert cmd == ["gemini", "-p", "Reply with OK.", "--output-format", "json"]


def test_kimi_contract_matches_current_cli_shape():
    contract = team_router.get_cli_contract("kimi")

    assert contract is not None
    assert contract["binary"] == "kimi"
    assert contract["auth_probe_kind"] == "none"
    assert contract["auth_probe"] is None

    cmd = team_router.build_non_interactive_command("kimi", "Reply with OK.", "/tmp/project")
    assert cmd == [
        "kimi",
        "--print",
        "--output-format",
        "text",
        "--final-message-only",
        "-w",
        "/tmp/project",
        "-p",
        "Reply with OK.",
    ]


def test_unknown_contract_returns_none():
    assert team_router.get_cli_contract("unknown") is None
    assert team_router.build_non_interactive_command("unknown", "hello", "/tmp/project") is None
