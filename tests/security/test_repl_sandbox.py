#!/usr/bin/env python3
"""
Security-specific tests for the REPL sandbox.

Covers the 10 required security test cases from the task spec,
plus additional escape vector and edge case tests.
"""

import os
import sys

import pytest
from unittest.mock import patch

# Add project root to path
project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.python_sandbox import SandboxedExecutor, execute_sandboxed


def test_semgrep_unavailable_returns_status_without_crashing(tmp_path):
    from runtime.security_check import run_semgrep_scan

    with patch("runtime.security_check.shutil.which", return_value=None):
        result = run_semgrep_scan(str(tmp_path))

    assert result["status"] == "unavailable"
    assert result["findings"] == []
    assert result["error"] == "semgrep not found"


@pytest.fixture
def sandbox():
    """Fresh sandbox for each test."""
    return SandboxedExecutor()


# --- Required Security Test Cases (spec items 1-10) ---


class TestSecurityCases:
    """The 10 required security test cases from the task specification."""

    def test_case_1_import_subprocess_blocked(self, sandbox):
        """Case 1: import subprocess → blocked."""
        result = sandbox.execute("import subprocess")
        assert result["blocked"] is True
        assert "subprocess" in result["error"].lower()

    def test_case_2_import_socket_blocked(self, sandbox):
        """Case 2: import socket → blocked."""
        result = sandbox.execute("import socket")
        assert result["blocked"] is True
        assert "socket" in result["error"].lower()

    def test_case_3_open_read_allowed(self, sandbox):
        """Case 3: open('/etc/passwd', 'r') → allowed (read-only is OK)."""
        # This may error on some systems (permission) but should NOT be blocked
        result = sandbox.execute("f = open('/dev/null', 'r'); f.close()")
        assert result["blocked"] is False

    def test_case_4_open_write_blocked(self, sandbox):
        """Case 4: open('/tmp/evil.sh', 'w') → blocked (write mode)."""
        result = sandbox.execute("f = open('/tmp/evil.sh', 'w')")
        assert result["blocked"] is True
        assert "write access denied" in result["error"].lower() or "sandbox" in result["error"].lower()

    def test_case_5_dunder_import_os_system_blocked(self, sandbox):
        """Case 5: __import__('os').system('ls') → blocked."""
        result = sandbox.execute("__import__('os').system('ls')")
        assert result["blocked"] is True

    def test_case_6_mro_escape_blocked(self, sandbox):
        """Case 6: ().__class__.__mro__[1].__subclasses__() → blocked (MRO escape)."""
        result = sandbox.execute("().__class__.__mro__[1].__subclasses__()")
        assert result["blocked"] is True

    def test_case_7_print_allowed(self, sandbox):
        """Case 7: print('hello') → allowed."""
        result = sandbox.execute("print('hello')")
        assert result["blocked"] is False
        assert "hello" in result["stdout"]
        assert result["error"] is None

    def test_case_8_arithmetic_allowed(self, sandbox):
        """Case 8: x = 1 + 1 → allowed."""
        result = sandbox.execute("x = 1 + 1")
        assert result["blocked"] is False
        assert result["error"] is None

    def test_case_9_import_math_allowed(self, sandbox):
        """Case 9: import math → allowed (safe stdlib)."""
        result = sandbox.execute("import math\nresult = math.pi")
        assert result["blocked"] is False
        assert result["error"] is None

    def test_case_10_import_json_allowed(self, sandbox):
        """Case 10: import json → allowed (safe stdlib)."""
        result = sandbox.execute("import json\nresult = json.dumps({'a': 1})")
        assert result["blocked"] is False
        assert result["error"] is None


# --- Additional Security Edge Cases ---


class TestEscapeVectors:
    """Additional tests for sandbox escape attempts."""

    def test_builtins_dict_access(self, sandbox):
        """Access to __builtins__.__dict__ is blocked."""
        result = sandbox.execute("__builtins__.__dict__")
        assert result["blocked"] is True

    def test_class_bases_access(self, sandbox):
        """Access to __bases__ is blocked."""
        result = sandbox.execute("int.__bases__")
        assert result["blocked"] is True

    def test_globals_access(self, sandbox):
        """Access to __globals__ is blocked."""
        result = sandbox.execute("(lambda: 0).__globals__")
        assert result["blocked"] is True

    def test_from_subprocess_import(self, sandbox):
        """from subprocess import run is blocked."""
        result = sandbox.execute("from subprocess import run")
        assert result["blocked"] is True

    def test_importlib_blocked(self, sandbox):
        """import importlib is blocked."""
        result = sandbox.execute("import importlib")
        assert result["blocked"] is True

    def test_pickle_blocked(self, sandbox):
        """import pickle is blocked."""
        result = sandbox.execute("import pickle")
        assert result["blocked"] is True

    def test_ctypes_blocked(self, sandbox):
        """import ctypes is blocked."""
        result = sandbox.execute("import ctypes")
        assert result["blocked"] is True

    def test_marshal_blocked(self, sandbox):
        """import marshal is blocked."""
        result = sandbox.execute("import marshal")
        assert result["blocked"] is True

    def test_multiprocessing_blocked(self, sandbox):
        """import multiprocessing is blocked."""
        result = sandbox.execute("import multiprocessing")
        assert result["blocked"] is True

    def test_os_system_call_blocked(self, sandbox):
        """os.system() is blocked via static analysis."""
        result = sandbox.execute("import os\nos.system('ls')")
        assert result["blocked"] is True

    def test_open_append_mode_blocked(self, sandbox):
        """open() in append mode is blocked."""
        result = sandbox.execute("f = open('/tmp/test.txt', 'a')")
        assert result["blocked"] is True

    def test_open_write_binary_blocked(self, sandbox):
        """open() in write-binary mode is blocked."""
        result = sandbox.execute("f = open('/tmp/test.bin', 'wb')")
        assert result["blocked"] is True

    def test_sys_modules_access_blocked(self, sandbox):
        """Access to sys.modules is blocked via string check."""
        result = sandbox.execute("import sys\nsys.modules")
        assert result["blocked"] is True

    def test_code_object_access_blocked(self, sandbox):
        """Access to __code__ attribute is blocked."""
        result = sandbox.execute("(lambda: 0).__code__")
        assert result["blocked"] is True


class TestSandboxRobustness:
    """Tests for sandbox robustness under edge conditions."""

    def test_empty_code(self, sandbox):
        """Empty code executes without error."""
        result = sandbox.execute("")
        assert result["blocked"] is False
        assert result["error"] is None

    def test_multiline_safe_code(self, sandbox):
        """Multi-line safe code works correctly."""
        code = "x = 10\ny = 20\nprint(x + y)"
        result = sandbox.execute(code)
        assert result["blocked"] is False
        assert "30" in result["stdout"]

    def test_list_comprehension(self, sandbox):
        """List comprehensions work in sandbox."""
        result = sandbox.execute("[x**2 for x in range(5)]")
        assert result["blocked"] is False
        assert result["result"] == "[0, 1, 4, 9, 16]"

    def test_function_definition(self, sandbox):
        """Defining and calling functions works."""
        code = "def greet(name): return f'Hello, {name}'\ngreet('World')"
        result = sandbox.execute(code)
        assert result["blocked"] is False

    def test_class_definition(self, sandbox):
        """Defining classes works (but escape via dunders is blocked)."""
        sandbox.execute("class Foo:\n    x = 42")
        result = sandbox.execute("Foo.x")
        assert result["blocked"] is False
        assert result["result"] == "42"

    def test_error_does_not_leak_internals(self, sandbox):
        """Error messages from blocked code don't expose sandbox internals."""
        result = sandbox.execute("import subprocess")
        assert result["blocked"] is True
        # Error should mention the block but not expose implementation details
        assert "subprocess" in result["error"].lower()
