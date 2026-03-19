from __future__ import annotations

from runtime.github_integration import get_github_token


def test_get_github_token_reads_omg_github_token() -> None:
    result = get_github_token(env={"OMG_GITHUB_TOKEN": "  ghp_example_token  "})

    assert result["status"] == "ok"
    assert result["token"] == "ghp_example_token"
    assert result["source"] == "env"


def test_get_github_token_missing_token_returns_direct_config_error() -> None:
    result = get_github_token(env={})

    assert result["status"] == "error"
    assert result["error_code"] == "GITHUB_TOKEN_MISSING"
    assert result["message"] == "OMG_GITHUB_TOKEN is not configured."
    missing = result.get("missing")
    assert isinstance(missing, list)
    assert missing == ["OMG_GITHUB_TOKEN"]


def test_get_github_token_blank_token_returns_direct_config_error() -> None:
    result = get_github_token(env={"OMG_GITHUB_TOKEN": "   "})

    assert result["status"] == "error"
    assert result["error_code"] == "GITHUB_TOKEN_MISSING"
    assert result["message"] == "OMG_GITHUB_TOKEN is not configured."
    missing = result.get("missing")
    assert isinstance(missing, list)
    assert missing == ["OMG_GITHUB_TOKEN"]
