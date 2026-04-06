from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hooks.policy_engine import evaluate_bash_command


def test_dangerous_inline_python_os_system_is_denied():
    result = evaluate_bash_command("python3 -c \"import os; os.system('whoami')\"")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_dangerous_inline_python_subprocess_is_denied():
    result = evaluate_bash_command(
        "python3 -c \"import subprocess; subprocess.run(['ls'])\""
    )
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_safe_inline_python_is_ask():
    result = evaluate_bash_command("python3 -c \"print('hello world')\"")
    assert result.action == "ask", f"Expected ask but got: {result.action}"


def test_dangerous_inline_node_child_process_is_denied():
    result = evaluate_bash_command(
        "node -e \"require('child_process').execSync('ls')\""
    )
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_safe_inline_node_is_ask():
    result = evaluate_bash_command('node -e "console.log(1)"')
    assert result.action == "ask", f"Expected ask but got: {result.action}"
