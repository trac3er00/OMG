"""Tests for centralized policy_engine decisions."""

from hooks.policy_engine import (
    evaluate_bash_command,
    evaluate_file_access,
    evaluate_supply_artifact,
)


def test_policy_engine_denies_rm_rf_root():
    decision = evaluate_bash_command("rm -rf /")
    assert decision.action == "deny"
    assert decision.risk_level == "critical"


def test_policy_engine_allows_safe_command():
    decision = evaluate_bash_command("ls -la")
    assert decision.action == "allow"


def test_policy_engine_denies_secret_file_access():
    decision = evaluate_file_access("Read", ".env.production")
    assert decision.action == "deny"


def test_policy_engine_allows_env_example_read():
    decision = evaluate_file_access("Read", ".env.example")
    assert decision.action == "allow"


def test_policy_engine_supply_critical_always_blocks():
    decision = evaluate_supply_artifact(
        {
            "id": "bad",
            "signer": "trusted",
            "checksum": "abc",
            "permissions": ["Read"],
            "static_scan": [{"severity": "critical", "rule": "secret-leak"}],
        },
        mode="warn_and_run",
    )
    assert decision.action == "deny"


def test_policy_engine_supply_warn_and_run_unsigned_is_ask():
    decision = evaluate_supply_artifact(
        {
            "id": "unsigned",
            "permissions": ["Read"],
            "static_scan": [],
        },
        mode="warn_and_run",
    )
    assert decision.action == "ask"
    assert decision.risk_level == "high"
