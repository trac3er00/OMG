#!/usr/bin/env python3
"""
Tests for tools/python_sandbox.py

Tests the security sandbox: static analysis, runtime restrictions,
blocked imports, escape detection, and feature flag gating.
"""

import os
import sys
from typing import Any
from unittest.mock import patch

import pytest

# Add project root to path
project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.python_sandbox import (
    SandboxedExecutor,
    create_sandbox,
    execute_budgeted_run,
    execute_sandboxed,
    get_code_violations,
    is_safe_code,
)

from lab.forge_runner import ForgeRunSpec, run_forge_sandboxed


def test_module_docstring_mentions_repl_only_scope():
    import tools.python_sandbox as python_sandbox

    doc = python_sandbox.__doc__ or ""
    assert "REPL-only" in doc


# --- TestIsSafeCode (static analysis) ---


class TestIsSafeCode:
    """Tests for is_safe_code() static analysis."""

    def test_safe_assignment(self):
        """Simple assignment is safe."""
        assert is_safe_code("x = 1 + 1") is True

    def test_safe_print(self):
        """Print statement is safe."""
        assert is_safe_code("print('hello')") is True

    def test_safe_math_import(self):
        """Importing safe stdlib modules is allowed."""
        assert is_safe_code("import math") is True

    def test_safe_json_import(self):
        """Importing json is allowed."""
        assert is_safe_code("import json") is True

    def test_blocked_subprocess_import(self):
        """Importing subprocess is blocked."""
        assert is_safe_code("import subprocess") is False

    def test_blocked_socket_import(self):
        """Importing socket is blocked."""
        assert is_safe_code("import socket") is False

    def test_blocked_ctypes_import(self):
        """Importing ctypes is blocked."""
        assert is_safe_code("import ctypes") is False

    def test_blocked_pickle_import(self):
        """Importing pickle is blocked."""
        assert is_safe_code("import pickle") is False

    def test_blocked_from_import(self):
        """from subprocess import ... is blocked."""
        assert is_safe_code("from subprocess import run") is False

    def test_blocked_dunder_import_call(self):
        """__import__() call is blocked."""
        assert is_safe_code("__import__('os')") is False

    def test_blocked_eval_call(self):
        """eval() call is blocked in static analysis."""
        assert is_safe_code("eval('1+1')") is False

    def test_blocked_exec_call(self):
        """exec() call is blocked in static analysis."""
        assert is_safe_code("exec('x = 1')") is False

    def test_syntax_error_passes(self):
        """Code with syntax errors passes static analysis (execution will report it)."""
        assert is_safe_code("def foo(") is True


# --- TestGetCodeViolations ---


class TestGetCodeViolations:
    """Tests for get_code_violations() detail inspection."""

    def test_no_violations_safe_code(self):
        """Safe code returns empty violations list."""
        violations = get_code_violations("x = 42")
        assert violations == []

    def test_subprocess_violation(self):
        """Subprocess import returns specific violation."""
        violations = get_code_violations("import subprocess")
        assert len(violations) == 1
        assert "subprocess" in violations[0]

    def test_multiple_violations(self):
        """Code with multiple issues returns all violations."""
        code = "import subprocess\nimport socket"
        violations = get_code_violations(code)
        assert len(violations) == 2

    def test_mro_escape_violation(self):
        """Accessing __mro__ is flagged."""
        violations = get_code_violations("x.__mro__")
        assert len(violations) >= 1
        assert any("__mro__" in v for v in violations)

    def test_subclasses_escape_violation(self):
        """Accessing __subclasses__ is flagged."""
        violations = get_code_violations("x.__subclasses__()")
        assert len(violations) >= 1
        assert any("__subclasses__" in v for v in violations)


# --- TestSandboxedExecutor ---


class TestSandboxedExecutor:
    """Tests for SandboxedExecutor class."""

    def test_basic_execution(self):
        """Basic code executes successfully."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("x = 1 + 1")
        assert result["error"] is None
        assert result["blocked"] is False

    def test_captures_stdout(self):
        """Stdout from print() is captured."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("print('hello sandbox')")
        assert "hello sandbox" in result["stdout"]
        assert result["blocked"] is False

    def test_expression_result(self):
        """Expression evaluation returns result."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("2 + 3")
        assert result["result"] == "5"
        assert result["blocked"] is False

    def test_blocks_subprocess_import(self):
        """Importing subprocess is blocked at both AST and runtime levels."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("import subprocess")
        assert result["blocked"] is True
        assert result["error"] is not None

    def test_blocks_socket_import(self):
        """Importing socket is blocked."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("import socket")
        assert result["blocked"] is True

    def test_allows_safe_import(self):
        """Importing safe modules like math works."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("import math\nresult = math.sqrt(4)")
        assert result["error"] is None
        assert result["blocked"] is False

    def test_blocks_file_write(self):
        """Opening a file in write mode is blocked."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("f = open('/tmp/evil.sh', 'w')")
        assert result["blocked"] is True
        assert "write access denied" in result["error"].lower() or "permission" in result["error"].lower()

    def test_allows_file_read(self):
        """Opening a file in read mode is allowed (may fail if file missing, but not blocked)."""
        sandbox = SandboxedExecutor()
        # Use a file that exists
        result = sandbox.execute("f = open('/dev/null', 'r'); f.close()")
        assert result["blocked"] is False

    def test_blocks_dunder_import(self):
        """__import__('os').system('ls') is blocked."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("__import__('os').system('ls')")
        assert result["blocked"] is True

    def test_blocks_mro_escape(self):
        """MRO-based sandbox escape is blocked."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("().__class__.__mro__[1].__subclasses__()")
        assert result["blocked"] is True

    def test_blocks_builtins_access(self):
        """Direct access to __builtins__ is blocked."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("__builtins__.__dict__")
        assert result["blocked"] is True

    def test_runtime_error_captured(self):
        """Runtime errors are captured, not blocked."""
        sandbox = SandboxedExecutor()
        result = sandbox.execute("1/0")
        assert result["error"] is not None
        assert "ZeroDivisionError" in result["error"]
        assert result["blocked"] is False

    def test_namespace_persistence(self):
        """Variables persist across executions in same sandbox."""
        sandbox = SandboxedExecutor()
        sandbox.execute("x = 42")
        result = sandbox.execute("print(x)")
        assert "42" in result["stdout"]

    def test_custom_blocked_imports(self):
        """Custom blocked imports set is honored."""
        sandbox = SandboxedExecutor(blocked_imports={"json"})
        result = sandbox.execute("import json")
        assert result["blocked"] is True


# --- TestCreateSandbox ---


class TestCreateSandbox:
    """Tests for create_sandbox() factory function."""

    def test_creates_executor(self):
        """Creates a SandboxedExecutor instance."""
        sandbox = create_sandbox()
        assert isinstance(sandbox, SandboxedExecutor)

    def test_with_existing_namespace(self):
        """Can provide an existing namespace."""
        ns = {"x": 42}
        sandbox = create_sandbox(namespace=ns)
        result = sandbox.execute("print(x)")
        assert "42" in result["stdout"]


# --- TestExecuteSandboxed ---


class TestExecuteSandboxed:
    """Tests for execute_sandboxed() convenience function."""

    def test_one_shot_execution(self):
        """One-shot execution works correctly."""
        result = execute_sandboxed("print('one-shot')")
        assert "one-shot" in result["stdout"]
        assert result["blocked"] is False

    def test_one_shot_blocks_dangerous(self):
        """One-shot execution blocks dangerous code."""
        result = execute_sandboxed("import subprocess")
        assert result["blocked"] is True


# --- TestFeatureFlag ---


class TestFeatureFlag:
    """Tests for sandbox feature flag behavior."""

    def test_flag_default_disabled(self):
        """Sandbox is disabled by default."""
        from tools.python_sandbox import _is_sandbox_enabled
        with patch.dict(os.environ, {}, clear=False):
            # Remove the env var if set
            env = dict(os.environ)
            env.pop("OMG_REPL_SANDBOX_ENABLED", None)
            with patch.dict(os.environ, env, clear=True):
                assert _is_sandbox_enabled() is False

    def test_flag_enabled_via_env(self):
        """Sandbox can be enabled via environment variable."""
        from tools.python_sandbox import _is_sandbox_enabled
        with patch.dict(os.environ, {"OMG_REPL_SANDBOX_ENABLED": "true"}):
            assert _is_sandbox_enabled() is True

    def test_flag_disabled_via_env(self):
        """Sandbox can be explicitly disabled via environment variable."""
        from tools.python_sandbox import _is_sandbox_enabled
        with patch.dict(os.environ, {"OMG_REPL_SANDBOX_ENABLED": "false"}):
            assert _is_sandbox_enabled() is False


# --- TestReplIntegration ---


class TestReplIntegration:
    """Tests for sandbox integration with python_repl.py."""

    python_repl: Any = None

    @pytest.fixture(autouse=True)
    def setup_repl(self):
        """Enable REPL and force stdlib backend."""
        import tools.python_repl as python_repl
        self.python_repl = python_repl
        python_repl._sessions.clear()
        python_repl._HAS_JUPYTER = False
        yield
        for session in list(python_repl._sessions.values()):
            backend = session.get("_backend")
            if backend:
                try:
                    backend.close()
                except Exception:
                    pass
        python_repl._sessions.clear()
        python_repl._HAS_JUPYTER = None

    def test_sandbox_routes_through_sandbox(self):
        """When sandbox enabled, execute_code uses sandboxed executor."""
        with patch.dict(os.environ, {
            "OMG_PYTHON_REPL_ENABLED": "true",
            "OMG_REPL_SANDBOX_ENABLED": "true",
        }):
            session = self.python_repl.start_repl_session(session_id="sandbox-test")
            result = self.python_repl.execute_code("sandbox-test", "print('sandboxed')")
            assert "sandboxed" in result["stdout"]
            assert "blocked" in result  # Sandbox adds "blocked" key

    def test_sandbox_blocks_in_repl(self):
        """Sandbox blocks dangerous code when routed through REPL."""
        with patch.dict(os.environ, {
            "OMG_PYTHON_REPL_ENABLED": "true",
            "OMG_REPL_SANDBOX_ENABLED": "true",
        }):
            session = self.python_repl.start_repl_session(session_id="sandbox-block")
            result = self.python_repl.execute_code("sandbox-block", "import subprocess")
            assert result.get("blocked") is True

    def test_no_sandbox_without_flag(self):
        """Without sandbox flag, execute_code works normally (no 'blocked' key)."""
        with patch.dict(os.environ, {
            "OMG_PYTHON_REPL_ENABLED": "true",
            "OMG_REPL_SANDBOX_ENABLED": "false",
        }):
            session = self.python_repl.start_repl_session(session_id="no-sandbox")
            result = self.python_repl.execute_code("no-sandbox", "x = 1 + 1")
            assert "blocked" not in result


class TestBudgetedSandboxExecution:
    def test_execute_budgeted_run_supports_multiprocess_evidence(self):
        result = execute_budgeted_run(
            trainer_code="print('trainer')",
            sidecar_code="print('sidecar')",
            time_budget_seconds=5,
            cost_budget_usd=3.5,
            gpu_allowed=True,
            outbound_allowlist=["allowed.example"],
            attempted_outbound=["allowed.example", "blocked.example"],
        )

        assert result["status"] == "success"
        assert result["sandbox_mode"] == "isolated-subprocess"
        assert result["process_count"] == 2
        assert result["outbound_blocked_count"] == 1
        assert result["network_calls_attempted"] == 2
        assert result["network_calls_allowed"] == 1
        assert result["budget"]["time_seconds"] == 5
        assert result["budget"]["cost_usd"] == 3.5

    def test_run_forge_sandboxed_returns_checkpoint_paths(self):
        spec = ForgeRunSpec(
            run_id="run-123",
            adapter="axolotl",
            budget={"time_seconds": 10, "cost_usd": 4.0, "gpu_allowed": True},
            outbound_allowlist=["allowed.example"],
            trainer_code="checkpoint_paths = ['runs/run-123/model.ckpt']",
            sidecar_code="print('sidecar ready')",
            attempted_outbound=["allowed.example"],
        )

        result = run_forge_sandboxed(spec)

        assert result.status == "success"
        assert result.checkpoint_paths == ["runs/run-123/model.ckpt"]
        assert result.evidence["isolation"]["process_count"] == 2
        assert result.evidence["budget"]["network_calls_allowed"] == 1
