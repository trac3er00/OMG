from __future__ import annotations

import json

from runtime.defense_state import DefenseState
from tests.hooks.helpers import (
    get_decision,
    make_bash_payload,
    make_file_payload,
    run_hook_json,
)


def test_firewall_bypass_mode_blocks_mandatory_network_ask() -> None:
    payload = make_bash_payload("curl https://example.com")
    payload["permission_mode"] = "dontAsk"
    out = run_hook_json("hooks/firewall.py", payload)
    assert get_decision(out or {}) == "deny"


def test_secret_guard_bypass_mode_blocks_mandatory_untrusted_write(tmp_path) -> None:
    state_path = tmp_path / ".omg" / "state" / "untrusted-content.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"active": True, "provenance": []}), encoding="utf-8"
    )

    payload = make_file_payload("Write", str(tmp_path / "docs" / "note.md"))
    payload["permission_mode"] = "bypassPermissions"
    out = run_hook_json(
        "hooks/secret-guard.py",
        payload,
        env_overrides={"CLAUDE_PROJECT_DIR": str(tmp_path), "OMG_TDD_GATE_STRICT": "0"},
    )
    assert get_decision(out or {}) == "deny"


def test_policy_engine_denies_secret_grep_even_without_bypass() -> None:
    out = run_hook_json(
        "hooks/firewall.py",
        make_bash_payload('grep -n "KEY" ~/.ssh/id_rsa'),
    )
    assert get_decision(out or {}) == "deny"


def test_policy_engine_detects_obfuscated_network_command() -> None:
    out = run_hook_json(
        "hooks/firewall.py", make_bash_payload("c''url https://example.com")
    )
    assert get_decision(out or {}) == "ask"


def test_defense_state_thresholds_are_configurable_from_policy_yaml(tmp_path) -> None:
    policy_path = tmp_path / ".omg" / "policy.yaml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        """
defense_state:
  thresholds:
    high:
      contamination_score: 0.1
""".strip()
        + "\n",
        encoding="utf-8",
    )

    state = DefenseState(str(tmp_path)).update(
        injection_hits=0,
        contamination_score=0.2,
        overthinking_score=0.0,
    )

    assert state["risk_level"] == "high"
    assert state["thresholds"]["high"]["contamination_score"] == 0.1
    assert state["threshold_source"] == ".omg/policy.yaml:defense_state.thresholds"
