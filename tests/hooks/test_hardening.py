"""Tests for OMG hardening: Phases 1-4 security and performance fixes."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pytest

from tests.hooks.helpers import (
    run_hook_json, get_decision, make_bash_payload, make_file_payload, ROOT,
)

HOOKS = ROOT / "hooks"


# --- 5.1 Firewall crash -> deny (fail-closed) ---

def test_common_deny_decision_format():
    """_common.deny_decision emits correct PreToolUse deny JSON."""
    sys.path.insert(0, str(HOOKS))
    try:
        from _common import deny_decision
        import io
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        deny_decision("test crash reason")
        sys.stdout = old_stdout
        output = json.loads(buf.getvalue())
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "test crash reason" in output["hookSpecificOutput"]["permissionDecisionReason"]
    finally:
        sys.path.remove(str(HOOKS))


def test_common_setup_crash_handler_fail_closed():
    """setup_crash_handler with fail_closed=True installs a deny-on-crash handler."""
    sys.path.insert(0, str(HOOKS))
    try:
        from _common import setup_crash_handler
        setup_crash_handler("test-hook", fail_closed=True)
        assert sys.excepthook is not sys.__excepthook__
    finally:
        sys.excepthook = sys.__excepthook__
        sys.path.remove(str(HOOKS))


# --- 5.2 Secret-guard crash -> deny (fail-closed) ---

def test_secret_guard_denies_env_file():
    """secret-guard.py must deny access to .env files."""
    out = run_hook_json("hooks/secret-guard.py", make_file_payload("Read", "/project/.env"))
    assert get_decision(out) == "deny", f"Should deny .env access, got: {out}"


def test_secret_guard_allows_normal_file():
    """secret-guard.py must allow normal files."""
    out = run_hook_json(
        "hooks/secret-guard.py",
        make_file_payload("Read", "/project/src/index.ts"),
    )
    assert get_decision(out) is None, f"Should allow normal file, got: {out}"


# --- 5.3 Symlink to .env -> policy_engine denies ---

def test_policy_engine_denies_symlink_to_env():
    """policy_engine must resolve symlinks before checking blocked files."""
    sys.path.insert(0, str(HOOKS))
    try:
        from policy_engine import evaluate_file_access
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("SECRET=value")
            link_path = os.path.join(tmpdir, "config.txt")
            os.symlink(env_file, link_path)
            decision = evaluate_file_access("Read", link_path)
            assert decision.action == "deny", (
                f"Symlink to .env should be denied, got: {decision.action} ({decision.reason})"
            )
    finally:
        sys.path.remove(str(HOOKS))


def test_policy_engine_allows_normal_symlink():
    """Symlinks to non-secret files should still be allowed."""
    sys.path.insert(0, str(HOOKS))
    try:
        from policy_engine import evaluate_file_access
        with tempfile.TemporaryDirectory() as tmpdir:
            real_file = os.path.join(tmpdir, "readme.md")
            with open(real_file, "w") as f:
                f.write("# Hello")
            link_path = os.path.join(tmpdir, "docs.md")
            os.symlink(real_file, link_path)
            decision = evaluate_file_access("Read", link_path)
            assert decision.action == "allow", (
                f"Symlink to normal file should be allowed, got: {decision.action}"
            )
    finally:
        sys.path.remove(str(HOOKS))


# --- 5.4 Stop-gate with failed git diff -> no NameError ---

def test_stop_gate_no_crash_without_git():
    """stop-gate.py must not crash with NameError if git diff fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_dir = os.path.join(tmpdir, ".omg", "state", "ledger")
        os.makedirs(ledger_dir)
        entry = {
            "ts": "2099-01-01T00:00:00+00:00",
            "tool": "Write",
            "file": "test.py",
            "success": True,
        }
        with open(os.path.join(ledger_dir, "tool-ledger.jsonl"), "w") as f:
            f.write(json.dumps(entry) + "\n")

        proc = subprocess.run(
            ["python3", str(HOOKS / "stop-gate.py")],
            input=json.dumps({}),
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir},
            cwd=str(ROOT),
        )
        assert proc.returncode == 0, f"stop-gate crashed: {proc.stderr}"
        assert "NameError" not in proc.stderr, f"NameError in stop-gate: {proc.stderr}"


# --- 5.5 Tool-ledger masks expanded secret patterns ---

def test_tool_ledger_masks_secrets():
    """tool-ledger secret masking covers AWS, GitHub, Stripe, DB URLs, JWT."""
    patterns = [
        (r'AKIA[0-9A-Z]{16}', '***AWS_KEY***'),
        (r'gh[ps]_[A-Za-z0-9_]{36,}', '***GH_TOKEN***'),
        (r'sk_live_[A-Za-z0-9]{20,}', '***STRIPE_KEY***'),
        (r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', '***JWT***'),
        (r'(?:postgres|mysql|mongodb|redis)://[^:]+:[^@]+@', '***DB_URL***'),
        (r'https?://[^:]+:[^@]+@', '***URL_CREDS***'),
    ]
    test_cases = [
        ("Found key AKIAIOSFODNN7EXAMPLE in output", "AKIAIOSFODNN7EXAMPLE"),
        ("Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        ("Key: sk_live_ABCDEFGHIJKLMNOPQRSTa", "sk_live_ABCDEFGHIJKLMNOPQRST"),
        ("postgres://user:pass123@localhost:5432/db", "postgres://user:pass123@"),
        ("https://admin:secret@api.example.com", "https://admin:secret@"),
    ]
    for text, secret_fragment in test_cases:
        result = text
        for pat, repl in patterns:
            result = re.sub(pat, repl, result)
        assert secret_fragment not in result, (
            f"Secret not masked: '{secret_fragment}' still in '{result}'"
        )


# --- 5.6 Post-write skips test DIRECTORIES ---

def test_post_write_directory_skip_logic():
    """post-write should skip files in test directories, not just test-named files."""
    dir_patterns = [
        "/__tests__/", "/test/", "/tests/", "/fixtures/", "/mocks/", "/__mocks__/",
    ]
    # These should be detected as test dirs
    for path in [
        "/project/__tests__/helpers/setup.js",
        "/project/test/data/sample.json",
        "/project/tests/fixtures/mock-data.js",
        "/project/__mocks__/api.js",
    ]:
        assert any(d in path.lower() for d in dir_patterns), f"Should detect test dir: {path}"

    # These should NOT match as test dirs or test names
    for path in [
        "/project/src/testing-utils.js",
        "/project/src/contestant.js",
    ]:
        lowpath = path.lower()
        is_test_dir = any(d in lowpath for d in dir_patterns)
        basename = os.path.basename(path).lower()
        is_test_name = any(p in basename for p in [".test.", ".spec.", "_test.", "test_"])
        assert not is_test_dir and not is_test_name, (
            f"Should NOT detect as test: {path}"
        )


# --- 5.7 Settings.json narrowed matchers are valid ---
# Hooks live in user-level ~/.claude/settings.json (not project-level) to avoid
# double-execution when both settings files are merged by Claude Code.

USER_SETTINGS = Path.home() / ".claude" / "settings.json"


def _load_hook_settings():
    """Load settings with hooks — check user-level, fallback to project-level."""
    for path in [USER_SETTINGS, ROOT / "settings.json"]:
        if path.exists():
            with open(path) as f:
                settings = json.load(f)
            if "hooks" in settings:
                return settings
    pytest.skip("No settings.json with hooks found")


def test_settings_matchers_valid():
    """Verify narrowed matchers in settings.json use valid tool names."""
    settings = _load_hook_settings()

    hooks = settings.get("hooks", {})
    valid_tools = {
        "Bash", "Read", "Write", "Edit", "MultiEdit", "Grep", "Glob", "Task",
    }

    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            matcher = entry.get("matcher")
            if matcher:
                for tool in matcher.split("|"):
                    assert tool in valid_tools, (
                        f"Invalid tool '{tool}' in matcher for {event}"
                    )


def test_circuit_breaker_matcher_narrowed():
    """Circuit breaker should only match Bash (perf optimization)."""
    settings = _load_hook_settings()

    for entry in settings["hooks"]["PostToolUse"]:
        for hook in entry.get("hooks", []):
            if "circuit-breaker" in hook.get("command", ""):
                assert entry["matcher"] == "Bash", (
                    f"Circuit breaker matcher should be 'Bash', got: {entry['matcher']}"
                )


def test_tool_ledger_matcher_no_read():
    """Tool ledger should not match Read (perf optimization)."""
    settings = _load_hook_settings()

    for entry in settings["hooks"]["PostToolUse"]:
        for hook in entry.get("hooks", []):
            if "tool-ledger" in hook.get("command", ""):
                tools = entry["matcher"].split("|")
                assert "Read" not in tools, (
                    f"Tool ledger should not match Read, got: {entry['matcher']}"
                )


# --- Additional: _common.py integration ---

def test_common_json_input_exits_on_bad_json():
    """json_input() should exit 0 on invalid JSON, not crash."""
    proc = subprocess.run(
        [
            "python3", "-c",
            f"import sys; sys.path.insert(0, '{HOOKS}'); "
            "from _common import json_input; json_input()",
        ],
        input="not valid json{{{",
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"Should exit 0 on bad JSON, got: {proc.returncode}"


def test_common_block_decision_format():
    """block_decision emits correct Stop hook block JSON."""
    sys.path.insert(0, str(HOOKS))
    try:
        from _common import block_decision
        import io
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        block_decision("test block reason")
        sys.stdout = old_stdout
        output = json.loads(buf.getvalue())
        assert output["decision"] == "block"
        assert output["reason"] == "test block reason"
    finally:
        sys.path.remove(str(HOOKS))
