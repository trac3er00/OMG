from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hooks.policy_engine import evaluate_bash_command


def test_find_delete_is_denied():
    result = evaluate_bash_command("find . -delete")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_find_exec_rm_is_denied():
    result = evaluate_bash_command("find . -name '*.py' -exec rm {} +")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_rsync_delete_is_denied():
    result = evaluate_bash_command("rsync --delete src/ dst/")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_shred_is_denied():
    result = evaluate_bash_command("shred -uz /tmp/secrets.txt")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_dd_dev_zero_is_denied():
    result = evaluate_bash_command("dd if=/dev/zero of=/dev/sda")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_rm_rf_dot_is_denied():
    result = evaluate_bash_command("rm -rf .")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_rm_rf_star_is_denied():
    result = evaluate_bash_command("rm -rf *")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_truncate_zero_is_denied():
    result = evaluate_bash_command("truncate -s 0 /tmp/file.txt")
    assert result.action == "deny", f"Expected deny but got: {result.action}"


def test_git_clean_is_ask_not_deny():
    result = evaluate_bash_command("git clean -fdx")
    assert result.action == "ask", f"Expected ask (not deny) but got: {result.action}"
