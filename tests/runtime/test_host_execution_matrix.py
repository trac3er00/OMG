"""Tests for provider ToC and host execution matrix in runtime.team_router."""
from __future__ import annotations

from runtime.team_router import get_host_execution_matrix, get_host_execution_profile


EXPECTED_HOSTS = {
    "claude_native",
    "codex_native",
    "gemini_native",
    "kimi_native",
    "claude_dispatch",
}

REQUIRED_FIELDS = {
    "provider",
    "host_mode",
    "native_omg_supported",
    "claude_call_supported",
    "hooks_supported",
    "skills_supported",
    "mcp_supported",
    "policy_mode",
    "policy_refs",
    "notes",
}

ALLOWED_POLICY_MODES = {"toc_ok", "manual_review_required", "unsupported"}


def test_host_execution_matrix_contains_expected_hosts():
    matrix = get_host_execution_matrix()

    assert EXPECTED_HOSTS.issubset(set(matrix))


def test_each_host_profile_has_required_fields():
    matrix = get_host_execution_matrix()

    for host_mode in EXPECTED_HOSTS:
        profile = matrix[host_mode]
        assert REQUIRED_FIELDS.issubset(set(profile))
        assert profile["host_mode"] == host_mode
        assert profile["policy_mode"] in ALLOWED_POLICY_MODES
        assert isinstance(profile["policy_refs"], list)
        assert profile["policy_refs"], f"{host_mode} should provide at least one policy reference"


def test_get_host_execution_profile_returns_specific_profile():
    profile = get_host_execution_profile("claude_dispatch")

    assert profile is not None
    assert profile["host_mode"] == "claude_dispatch"
    assert profile["claude_call_supported"] is True
    assert profile["native_omg_supported"] is False


def test_external_native_hosts_are_model_specific():
    for host_mode, provider in {
        "codex_native": "codex",
        "gemini_native": "gemini",
        "kimi_native": "kimi",
    }.items():
        profile = get_host_execution_profile(host_mode)
        assert profile is not None
        assert profile["provider"] == provider
        assert profile["host_mode"] == host_mode


def test_unknown_host_profile_returns_none():
    assert get_host_execution_profile("does_not_exist") is None


def test_verified_policy_modes_match_current_official_sources():
    assert get_host_execution_profile("codex_native")["policy_mode"] == "toc_ok"
    assert get_host_execution_profile("gemini_native")["policy_mode"] == "toc_ok"
    assert get_host_execution_profile("kimi_native")["policy_mode"] == "manual_review_required"
    assert get_host_execution_profile("claude_dispatch")["policy_mode"] == "manual_review_required"
