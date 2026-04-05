from __future__ import annotations

import hooks.policy_engine as policy_engine


def test_evaluate_bash_command_uses_precompiled_patterns(monkeypatch) -> None:
    def _fail_re_search(*_args, **_kwargs):
        raise AssertionError(
            "evaluate_bash_command should use precompiled regex patterns"
        )

    monkeypatch.setattr(policy_engine.re, "search", _fail_re_search)
    decision = policy_engine.evaluate_bash_command("ls -la")
    assert decision.action == "allow"
