#!/usr/bin/env python3
"""
Tests for hooks/prompt-enhancer.py — zero-injection optimization and budget cap.
"""
import json
import subprocess
import sys
import os

import pytest

HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
PROMPT_ENHANCER = os.path.join(HOOKS_DIR, "prompt-enhancer.py")

sys.path.insert(0, HOOKS_DIR)
from _budget import BUDGET_PROMPT_TOTAL


def _run_enhancer(prompt: str, project_dir: str | None = None, timeout: int = 10) -> str:
    """Run prompt-enhancer.py with the given prompt, return stdout."""
    data = {"user_message": prompt}
    env = os.environ.copy()
    if project_dir:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    result = subprocess.run(
        [sys.executable, PROMPT_ENHANCER],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return result.stdout.strip()


class TestZeroInjection:
    """Simple prompts with no keyword signals should produce zero injection."""

    @pytest.mark.parametrize("prompt", [
        "hello",
        "hi",
        "ok",
        "thanks",
        "yes",
        "no",
        "goodbye",
        "hey there",
    ])
    def test_simple_prompt_no_output(self, prompt, tmp_path):
        """A short prompt with no keyword signals produces empty output."""
        output = _run_enhancer(prompt, project_dir=str(tmp_path))
        assert output == "", f"Expected empty output for '{prompt}', got: {output!r}"

    def test_single_word_hello(self, tmp_path):
        """Explicit: 'hello' must produce zero contextInjection."""
        output = _run_enhancer("hello", project_dir=str(tmp_path))
        if output:
            parsed = json.loads(output)
            # If somehow we get output, contextInjection must be empty
            assert parsed.get("contextInjection", "") == ""
        else:
            assert output == ""


class TestBudgetHardCap:
    """Injections must stay within BUDGET_PROMPT_TOTAL (1000 chars)."""

    def test_keyword_prompt_within_budget(self, tmp_path):
        """A prompt with coding keywords produces output <= 1000 chars."""
        # Create minimal .omg structure
        (tmp_path / ".omg" / "state" / "ledger").mkdir(parents=True)
        (tmp_path / ".omg" / "knowledge").mkdir(parents=True)

        prompt = "fix the bug in the auth module and implement error handling"
        output = _run_enhancer(prompt, project_dir=str(tmp_path))
        if output:
            parsed = json.loads(output)
            injection = parsed.get("contextInjection", "")
            assert len(injection) <= BUDGET_PROMPT_TOTAL, (
                f"Injection length {len(injection)} exceeds budget {BUDGET_PROMPT_TOTAL}"
            )

    def test_complex_prompt_capped_at_budget(self, tmp_path):
        """Even with many keywords, output never exceeds BUDGET_PROMPT_TOTAL."""
        (tmp_path / ".omg" / "state" / "ledger").mkdir(parents=True)
        (tmp_path / ".omg" / "knowledge").mkdir(parents=True)

        # Trigger as many signals as possible
        prompt = (
            "fix the bug and implement auth login with jwt oauth "
            "refactor the code and review security "
            "create a new domain module and deploy "
            "the screenshot shows a visual bug in css layout ui ux "
            "stuck on the same error crash ralph ulw crazy "
            "continue where I left off and then fix all files "
            "全体 수정 구현 버그 에러 고쳐 리팩토링 리뷰 "
            "implement build create add update refactor migrate deploy rewrite redesign "
            "entire project full stack frontend and backend end to end "
        )
        output = _run_enhancer(prompt, project_dir=str(tmp_path))
        if output:
            parsed = json.loads(output)
            injection = parsed.get("contextInjection", "")
            assert len(injection) <= BUDGET_PROMPT_TOTAL, (
                f"Injection length {len(injection)} exceeds budget {BUDGET_PROMPT_TOTAL}"
            )

    def test_budget_constant_is_1000(self):
        """Verify budget constant value."""
        assert BUDGET_PROMPT_TOTAL == 1000


class TestKeywordDetection:
    """Prompts with keywords DO get injections (non-zero output)."""

    @pytest.mark.parametrize("prompt", [
        "fix the broken login page",
        "implement a new feature",
        "review the auth module",
        "refactor the database layer",
    ])
    def test_keyword_prompt_produces_output(self, prompt, tmp_path):
        """Prompts with coding keywords should produce non-empty output."""
        (tmp_path / ".omg" / "state" / "ledger").mkdir(parents=True)
        (tmp_path / ".omg" / "knowledge").mkdir(parents=True)

        output = _run_enhancer(prompt, project_dir=str(tmp_path))
        assert output != "", f"Expected non-empty output for '{prompt}'"
        parsed = json.loads(output)
        assert "contextInjection" in parsed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
