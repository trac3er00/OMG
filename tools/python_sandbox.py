#!/usr/bin/env python3
"""Security Sandbox for OMG Python REPL (REPL-only).

Provides a restricted execution environment that blocks dangerous operations:
- Dangerous imports (subprocess, socket, ctypes, etc.)
- File write access
- Network operations
- Sandbox escape patterns (__class__.__mro__, __subclasses__, etc.)
- Dangerous builtins (__import__, eval, exec, compile, etc.)

Feature flag: OMG_REPL_SANDBOX_ENABLED (default: False)

This module is the concrete REPL-only sandbox implementation. Broader sandbox
policy is mediated by hook-level controls in hooks/firewall.py and
hooks/secret-guard.py.

Usage:
    from tools.python_sandbox import execute_sandboxed, is_safe_code, create_sandbox

    result = execute_sandboxed("print('hello')")
    # => {"stdout": "hello\\n", "stderr": "", "result": None, "error": None, "blocked": False}

    safe = is_safe_code("import subprocess")
    # => False
"""

import ast
import contextlib
import io
import json
import os
import subprocess
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Set


# --- Lazy imports for hooks/_common.py ---

_get_feature_flag = None


def _ensure_imports():
    """Lazy import feature flag from hooks/_common.py."""
    global _get_feature_flag
    if _get_feature_flag is not None:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from hooks._common import get_feature_flag as _gff
        _get_feature_flag = _gff
    except ImportError:
        # Optional: hooks._common not available
        _get_feature_flag = None


def _is_sandbox_enabled() -> bool:
    """Check if sandbox feature is enabled."""
    # Fast path: check env var directly
    env_val = os.environ.get("OMG_REPL_SANDBOX_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    # Fallback to hooks/_common.get_feature_flag
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("REPL_SANDBOX", default=False)
    return False


# --- Blocked imports configuration ---

_DEFAULT_BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "subprocess",
    "socket",
    "ctypes",
    "importlib",
    "pickle",
    "marshal",
    "shelve",
    "multiprocessing",
    "threading",
    "pty",
    "shutil",
    "signal",
    "resource",
    "code",
    "codeop",
})


def _get_blocked_imports() -> Set[str]:
    """Get the set of blocked import names, configurable via env var."""
    env_val = os.environ.get("OMG_SANDBOX_BLOCKED_IMPORTS", "").strip()
    if env_val:
        custom = frozenset(name.strip() for name in env_val.split(",") if name.strip())
        return set(_DEFAULT_BLOCKED_IMPORTS | custom)
    return set(_DEFAULT_BLOCKED_IMPORTS)


# --- Blocked builtins ---

_DANGEROUS_BUILTINS: frozenset[str] = frozenset({
    "__import__",
    "eval",
    "exec",
    "compile",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "breakpoint",
    "exit",
    "quit",
    "help",
    "input",
    "memoryview",
})


# --- Sandbox escape patterns ---

_ESCAPE_PATTERNS: List[str] = [
    "__class__",
    "__mro__",
    "__subclasses__",
    "__bases__",
    "__builtins__",
    "__globals__",
    "__code__",
    "__func__",
    "__self__",
    "__dict__",
    "__init_subclass__",
    "__set_name__",
    "__class_getitem__",
    "os.system",
    "os.popen",
    "os.exec",
    "os.spawn",
    "os.fork",
    "sys.modules",
    "sys._getframe",
]


# --- AST-based static analysis ---

class _SafetyChecker(ast.NodeVisitor):
    """AST visitor that checks for dangerous code patterns."""

    def __init__(self, blocked_imports: Set[str]):
        self.blocked_imports = blocked_imports
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            if module_name in self.blocked_imports:
                self.violations.append(
                    f"Blocked import: '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            module_name = node.module.split(".")[0]
            if module_name in self.blocked_imports:
                self.violations.append(
                    f"Blocked import: 'from {node.module}'"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check for __import__() calls
        if isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                self.violations.append("Blocked: __import__() call")
            elif node.func.id in ("eval", "exec", "compile"):
                self.violations.append(
                    f"Blocked: {node.func.id}() call"
                )
        # Check for os.system(), os.popen() etc
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                full_name = f"{node.func.value.id}.{node.func.attr}"
                if full_name in ("os.system", "os.popen", "os.execvp",
                                 "os.execv", "os.execve", "os.spawnl",
                                 "os.spawnle", "os.fork"):
                    self.violations.append(f"Blocked: {full_name}() call")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Check for sandbox escape attributes
        if node.attr in ("__class__", "__mro__", "__subclasses__",
                         "__bases__", "__builtins__", "__globals__",
                         "__code__", "__func__", "__self__",
                         "__init_subclass__", "__set_name__",
                         "__class_getitem__"):
            self.violations.append(
                f"Blocked: access to '{node.attr}' (sandbox escape)"
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Block direct access to dangerous names
        if node.id == "__builtins__":
            self.violations.append("Blocked: access to '__builtins__'")
        self.generic_visit(node)


def is_safe_code(code: str) -> bool:
    """Static analysis check: return True if code appears safe to execute.

    Parses the code into an AST and checks for:
    - Import statements with blocked modules
    - Call nodes invoking dangerous functions
    - Attribute access to sandbox escape dunder methods

    Args:
        code: Python source code to check

    Returns:
        True if code passes static analysis, False if dangerous patterns found
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Let the actual execution report the syntax error
        return True

    blocked_imports = _get_blocked_imports()
    checker = _SafetyChecker(blocked_imports)
    checker.visit(tree)
    return len(checker.violations) == 0


def get_code_violations(code: str) -> List[str]:
    """Return list of safety violations found in code.

    Args:
        code: Python source code to check

    Returns:
        List of violation description strings (empty if safe)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    blocked_imports = _get_blocked_imports()
    checker = _SafetyChecker(blocked_imports)
    checker.visit(tree)
    return checker.violations


# --- String-level escape detection ---

def _check_string_escapes(code: str) -> Optional[str]:
    """Check for sandbox escape patterns in raw code string.

    This catches patterns that might not appear in the AST
    (e.g., constructed via string manipulation).

    Args:
        code: Raw source code string

    Returns:
        Violation description if found, None if clean
    """
    for pattern in _ESCAPE_PATTERNS:
        if pattern in code:
            return f"Blocked: suspicious pattern '{pattern}' detected"
    return None


# --- Restricted open() ---

_ALLOWED_READ_MODES: frozenset[str] = frozenset({
    "r", "rb", "rt",
    "",  # default mode is 'r'
})


def _restricted_open(name, mode="r", *args, **kwargs):
    """Restricted open() that only allows read-mode file access.

    Args:
        name: File path to open
        mode: File open mode (only read modes allowed)
        *args: Passed through to builtin open
        **kwargs: Passed through to builtin open

    Returns:
        File object (read-only)

    Raises:
        PermissionError: If write/append mode is attempted
    """
    # Normalize mode string
    clean_mode = mode.strip().lower()
    if clean_mode not in _ALLOWED_READ_MODES:
        raise PermissionError(
            f"Sandbox: write access denied (mode='{mode}'). "
            f"Only read modes are allowed: {sorted(_ALLOWED_READ_MODES - {''})}"
        )
    return open(name, mode, *args, **kwargs)


# --- Restricted __import__ ---

def _make_restricted_import(blocked_imports: Set[str]):
    """Create a restricted __import__ function that blocks dangerous modules.

    Args:
        blocked_imports: Set of module names to block

    Returns:
        A replacement __import__ function
    """
    _real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _restricted_import(name, *args, **kwargs):
        top_level = name.split(".")[0]
        if top_level in blocked_imports:
            raise ImportError(
                f"Sandbox: import of '{name}' is blocked. "
                f"Module '{top_level}' is on the restricted list."
            )
        return _real_import(name, *args, **kwargs)

    return _restricted_import


# --- Safe builtins construction ---

def _build_safe_builtins(blocked_imports: Set[str]) -> Dict[str, Any]:
    """Build a restricted __builtins__ dict for sandbox execution.

    Removes dangerous builtins and replaces open/__import__ with
    restricted versions.

    Args:
        blocked_imports: Set of module names to block in __import__

    Returns:
        Dict of safe builtin names to their values
    """
    # Start from a copy of real builtins
    if isinstance(__builtins__, dict):
        safe = dict(__builtins__)
    else:
        safe = {k: getattr(__builtins__, k) for k in dir(__builtins__)
                if not k.startswith("_") or k == "__name__"}
        # Include common dunders that are needed
        for attr in ("__build_class__", "__name__", "__spec__"):
            if hasattr(__builtins__, attr):
                safe[attr] = getattr(__builtins__, attr)

    # Remove dangerous builtins
    for name in _DANGEROUS_BUILTINS:
        safe.pop(name, None)

    # Replace open with restricted version
    safe["open"] = _restricted_open

    # Replace __import__ with restricted version
    safe["__import__"] = _make_restricted_import(blocked_imports)

    # Ensure print is available
    safe["print"] = print

    return safe


# --- SandboxedExecutor ---

class SandboxedExecutor:
    """Restricted Python execution environment.

    Creates an isolated namespace with restricted builtins that
    prevents dangerous operations like system calls, network access,
    and file writes.

    Usage:
        sandbox = SandboxedExecutor()
        result = sandbox.execute("print('hello')")
    """

    def __init__(
        self,
        namespace: Optional[Dict[str, Any]] = None,
        blocked_imports: Optional[Set[str]] = None,
        extra_blocked_builtins: Optional[Set[str]] = None,
    ):
        """Initialize the sandboxed executor.

        Args:
            namespace: Optional existing namespace to sandbox (will be modified)
            blocked_imports: Override the default blocked imports set
            extra_blocked_builtins: Additional builtins to block beyond defaults
        """
        self._blocked_imports = blocked_imports or _get_blocked_imports()

        # Build safe builtins
        self._safe_builtins = _build_safe_builtins(self._blocked_imports)

        # Remove extra builtins if requested
        if extra_blocked_builtins:
            for name in extra_blocked_builtins:
                self._safe_builtins.pop(name, None)

        # Initialize or adopt namespace
        if namespace is not None:
            self._namespace = namespace
            self._namespace["__builtins__"] = self._safe_builtins
        else:
            self._namespace = {"__builtins__": self._safe_builtins}

    @property
    def namespace(self) -> Dict[str, Any]:
        """The execution namespace."""
        return self._namespace

    def execute(self, code: str) -> Dict[str, Any]:
        """Execute code in the sandbox.

        Performs both static analysis and runtime restriction.

        Args:
            code: Python source code to execute

        Returns:
            Dict with keys:
                stdout: Captured stdout output
                stderr: Captured stderr output
                result: Expression result (repr) or None
                error: Error message or None
                blocked: True if code was blocked by safety checks
        """
        # Step 1: String-level escape check
        escape_violation = _check_string_escapes(code)
        if escape_violation:
            return {
                "stdout": "",
                "stderr": "",
                "result": None,
                "error": escape_violation,
                "blocked": True,
            }

        # Step 2: AST-level static analysis
        violations = get_code_violations(code)
        if violations:
            return {
                "stdout": "",
                "stderr": "",
                "result": None,
                "error": "Security violation: " + "; ".join(violations),
                "blocked": True,
            }

        # Step 3: Execute in restricted namespace
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        result = None
        error = None

        try:
            with contextlib.redirect_stdout(stdout_buf), \
                 contextlib.redirect_stderr(stderr_buf):
                # Try expression eval first
                try:
                    tree = ast.parse(code, mode="eval")
                    compiled = compile(tree, "<sandbox>", "eval")
                    result_val = eval(compiled, self._namespace)  # noqa: S307
                    if result_val is not None:
                        result = repr(result_val)
                except SyntaxError:
                    # Fall back to exec for statements
                    tree = ast.parse(code, mode="exec")
                    compiled = compile(tree, "<sandbox>", "exec")
                    exec(compiled, self._namespace)  # noqa: S102
        except ImportError as e:
            if "blocked" in str(e).lower() or "restricted" in str(e).lower():
                return {
                    "stdout": stdout_buf.getvalue(),
                    "stderr": stderr_buf.getvalue(),
                    "result": None,
                    "error": str(e),
                    "blocked": True,
                }
            error = traceback.format_exc()
        except PermissionError as e:
            if "sandbox" in str(e).lower():
                return {
                    "stdout": stdout_buf.getvalue(),
                    "stderr": stderr_buf.getvalue(),
                    "result": None,
                    "error": str(e),
                    "blocked": True,
                }
            error = traceback.format_exc()
        except Exception:
            error = traceback.format_exc()

        return {
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "result": result,
            "error": error,
            "blocked": False,
        }


# --- Module-level convenience functions ---

def create_sandbox(
    namespace: Optional[Dict[str, Any]] = None,
    blocked_imports: Optional[Set[str]] = None,
) -> SandboxedExecutor:
    """Create a sandboxed executor with restricted execution environment.

    Args:
        namespace: Optional existing namespace to use (will be restricted)
        blocked_imports: Optional override for blocked imports set

    Returns:
        SandboxedExecutor instance ready for use
    """
    return SandboxedExecutor(
        namespace=namespace,
        blocked_imports=blocked_imports,
    )


def execute_sandboxed(
    code: str,
    namespace: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute code in a one-shot sandbox.

    Convenience function that creates a temporary sandbox and executes code.

    Args:
        code: Python source code to execute
        namespace: Optional namespace dict to execute in

    Returns:
        Dict with keys: stdout, stderr, result, error, blocked
    """
    sandbox = create_sandbox(namespace=namespace)
    return sandbox.execute(code)


def _run_isolated_python(code: str, timeout_seconds: int) -> Dict[str, Any]:
    marker = "__OMG_SANDBOX_RESULT__"
    wrapper = (
        "import json,os,traceback\n"
        "CODE = os.environ.get('CODE', '')\n"
        "ns = {}\n"
        "payload = {'status': 'success', 'error': None, 'checkpoint_paths': [], 'requested_gpu': False}\n"
        "try:\n"
        "    exec(CODE, ns)\n"
        "    cp = ns.get('checkpoint_paths', [])\n"
        "    payload['checkpoint_paths'] = [str(v) for v in cp] if isinstance(cp, list) else []\n"
        "    payload['requested_gpu'] = bool(ns.get('requested_gpu', False))\n"
        "except Exception:\n"
        "    payload['status'] = 'error'\n"
        "    payload['error'] = traceback.format_exc()\n"
        f"print('{marker}' + json.dumps(payload, ensure_ascii=True))\n"
    )
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-I", "-c", wrapper],
        capture_output=True,
        text=True,
        timeout=max(1, int(timeout_seconds)),
        check=False,
        env={**os.environ, "CODE": code},
    )
    elapsed = max(0.0, time.monotonic() - started)

    payload: Dict[str, Any] = {
        "status": "error" if result.returncode else "success",
        "error": None,
        "checkpoint_paths": [],
        "requested_gpu": False,
    }
    lines = result.stdout.splitlines()
    for line in reversed(lines):
        if line.startswith(marker):
            raw = line[len(marker):]
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, dict):
                    payload.update(decoded)
            except json.JSONDecodeError:
                payload["status"] = "error"
                payload["error"] = "sandbox result parse failure"
            break

    visible_stdout = "\n".join(line for line in lines if not line.startswith(marker))
    if visible_stdout:
        visible_stdout += "\n"

    return {
        "status": payload.get("status", "error"),
        "error": payload.get("error"),
        "checkpoint_paths": payload.get("checkpoint_paths", []),
        "requested_gpu": bool(payload.get("requested_gpu", False)),
        "stdout": visible_stdout,
        "stderr": result.stderr,
        "elapsed_seconds": elapsed,
        "exit_code": result.returncode,
    }


def _exec_kernel_metadata() -> Dict[str, Any]:
    try:
        from runtime.exec_kernel import get_exec_kernel
        from runtime.release_run_coordinator import resolve_current_run_id

        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        run_id = resolve_current_run_id(project_dir)
        kernel = get_exec_kernel(project_dir)
        return {
            "run_id": run_id,
            "enabled": kernel.enabled,
            "attach_log": kernel.attach_log(run_id) if run_id else "",
            "evidence_hooks": [".omg/evidence/subagents"],
        }
    except Exception:
        return {"run_id": None, "enabled": False, "attach_log": "", "evidence_hooks": []}


def execute_budgeted_run(
    *,
    trainer_code: str,
    sidecar_code: Optional[str] = None,
    time_budget_seconds: int = 60,
    cost_budget_usd: float = 1.0,
    gpu_allowed: bool = False,
    outbound_allowlist: Optional[List[str]] = None,
    attempted_outbound: Optional[List[str]] = None,
) -> Dict[str, Any]:
    allowlist = set(outbound_allowlist or [])
    attempted = [str(target) for target in (attempted_outbound or [])]
    blocked_targets = [target for target in attempted if target not in allowlist]
    allowed_targets = [target for target in attempted if target in allowlist]

    started = time.monotonic()
    trainer_result = _run_isolated_python(trainer_code, max(1, time_budget_seconds))
    sidecar_result: Dict[str, Any] | None = None

    elapsed = trainer_result["elapsed_seconds"]
    if sidecar_code:
        remaining = max(1, int(time_budget_seconds - elapsed))
        sidecar_result = _run_isolated_python(sidecar_code, remaining)
        elapsed += float(sidecar_result.get("elapsed_seconds", 0.0))

    elapsed_total = max(elapsed, time.monotonic() - started)
    estimated_cost = round(elapsed_total * (0.02 if gpu_allowed else 0.01), 4)

    status = "success"
    error = None
    if trainer_result["status"] != "success":
        status = "error"
        error = trainer_result.get("error")
    elif sidecar_result and sidecar_result["status"] != "success":
        status = "error"
        error = sidecar_result.get("error")
    elif elapsed_total > float(time_budget_seconds):
        status = "blocked"
        error = "time budget exceeded"
    elif estimated_cost > float(cost_budget_usd):
        status = "blocked"
        error = "cost budget exceeded"

    checkpoint_paths = list(trainer_result.get("checkpoint_paths", []))
    if sidecar_result:
        checkpoint_paths.extend(sidecar_result.get("checkpoint_paths", []))

    return {
        "status": status,
        "error": error,
        "sandbox_mode": "isolated-subprocess",
        "process_count": 2 if sidecar_result else 1,
        "outbound_blocked_count": len(blocked_targets),
        "network_calls_attempted": len(attempted),
        "network_calls_allowed": len(allowed_targets),
        "blocked_targets": blocked_targets,
        "allowed_targets": allowed_targets,
        "time_used_seconds": round(elapsed_total, 4),
        "estimated_cost_usd": estimated_cost,
        "checkpoint_paths": checkpoint_paths,
        "requested_gpu": bool(trainer_result.get("requested_gpu", False)),
        "budget": {
            "time_seconds": int(time_budget_seconds),
            "cost_usd": float(cost_budget_usd),
            "gpu_allowed": bool(gpu_allowed),
        },
        "trainer": trainer_result,
        "sidecar": sidecar_result,
        "exec_kernel": _exec_kernel_metadata(),
    }


# --- CLI Interface ---

def _cli_main():
    """CLI entry point for python_sandbox.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG Python Sandbox — restricted execution environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--exec", dest="code", help="Execute Python code in sandbox")
    parser.add_argument(
        "--check", dest="check_code", help="Static safety check only (no execution)"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show sandbox status and configuration"
    )

    args = parser.parse_args()

    if args.status:
        import json
        status = {
            "sandbox_enabled": _is_sandbox_enabled(),
            "blocked_imports": sorted(_get_blocked_imports()),
            "dangerous_builtins": sorted(_DANGEROUS_BUILTINS),
            "escape_patterns_count": len(_ESCAPE_PATTERNS),
        }
        print(json.dumps(status, indent=2))
        return

    if args.check_code:
        import json
        violations = get_code_violations(args.check_code)
        result = {
            "safe": len(violations) == 0,
            "violations": violations,
        }
        print(json.dumps(result, indent=2))
        return

    if args.code:
        import json
        result = execute_sandboxed(args.code)
        print(json.dumps(result, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
