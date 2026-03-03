#!/usr/bin/env python3
"""
IPython Kernel Integration for OMG

Provides persistent REPL sessions with IPython kernel support (optional)
and stdlib fallback via code.InteractiveConsole.

Feature flag: OMG_PYTHON_REPL_ENABLED (default: False)
"""

import ast
import code
import contextlib
import io
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Union


# --- Lazy imports for hooks/_common.py ---

_get_feature_flag = None
_atomic_json_write = None


def _ensure_imports():
    """Lazy import feature flag and atomic write from hooks/_common.py."""
    global _get_feature_flag, _atomic_json_write
    if _get_feature_flag is not None:
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from hooks._common import get_feature_flag as _gff
        from hooks._common import atomic_json_write as _ajw
        _get_feature_flag = _gff
        _atomic_json_write = _ajw
    except ImportError:
        pass


# --- Optional jupyter_client ---

_jupyter_client = None
_HAS_JUPYTER: Optional[bool] = None


def _check_jupyter() -> bool:
    """Check if jupyter_client is available (cached after first check)."""
    global _HAS_JUPYTER, _jupyter_client
    if _HAS_JUPYTER is None:
        try:
            import jupyter_client as _jc
            _jupyter_client = _jc
            _HAS_JUPYTER = True
        except ImportError:
            _HAS_JUPYTER = False
    return _HAS_JUPYTER


# --- Feature flag ---

def _is_enabled() -> bool:
    """Check if Python REPL feature is enabled."""
    # Fast path: check env var directly
    env_val = os.environ.get("OMG_PYTHON_REPL_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    # Fallback to hooks/_common.get_feature_flag
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("PYTHON_REPL", default=False)
    return False


def _get_sandbox_flag() -> bool:
    """Check if sandbox mode is enabled for the REPL."""
    env_val = os.environ.get("OMG_REPL_SANDBOX_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("REPL_SANDBOX", default=False)
    return False


def _get_helpers_flag() -> bool:
    """Check if REPL prelude helpers are enabled."""
    env_val = os.environ.get("OMG_REPL_HELPERS_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    _ensure_imports()
    if _get_feature_flag is not None:
        return _get_feature_flag("REPL_HELPERS", default=False)
    return False


def _build_prelude_namespace() -> dict:
    """Build the prelude namespace with helper functions for REPL sessions.

    Returns a dict of helper functions injected into every session when
    OMG_REPL_HELPERS_ENABLED=true. All helpers use stdlib only and handle
    exceptions gracefully.
    """
    import re as _re

    def read_file(path: str) -> str:
        """Read file content. Returns empty string on error."""
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return ""

    def write_file(path: str, content: str) -> bool:
        """Write content to file. Blocked in sandbox mode. Returns False on error."""
        if _get_sandbox_flag():
            return False
        try:
            with open(path, "w") as f:
                f.write(content)
            return True
        except Exception:
            return False

    def lines(path: str) -> list:
        """Read file lines as list. Returns empty list on error."""
        try:
            with open(path, "r") as f:
                return f.read().splitlines()
        except Exception:
            return []

    def search_code(pattern: str, path: str = ".", ext=None) -> list:
        """Grep-like search across files. Returns list of {file, line, match} dicts."""
        results = []
        try:
            compiled = _re.compile(pattern)
            for root, _dirs, files in os.walk(path):
                for fname in files:
                    if ext is not None and not fname.endswith(ext):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", errors="ignore") as f:
                            for lineno, line_text in enumerate(f, 1):
                                if compiled.search(line_text):
                                    results.append({
                                        "file": fpath,
                                        "line": lineno,
                                        "match": line_text.rstrip(),
                                    })
                    except Exception:
                        continue
        except Exception:
            pass
        return results

    def grep(pattern: str, text: str) -> list:
        """Regex grep on a string. Returns matching lines."""
        try:
            compiled = _re.compile(pattern)
            return [line for line in text.splitlines() if compiled.search(line)]
        except Exception:
            return []

    def insert_at(lines_list: list, index: int, new_line: str) -> list:
        """Insert a line at index. Returns new list."""
        try:
            result = list(lines_list)
            result.insert(index, new_line)
            return result
        except Exception:
            return list(lines_list)

    def delete_lines(lines_list: list, start: int, end: int) -> list:
        """Delete lines from start to end (exclusive). Returns new list."""
        try:
            result = list(lines_list)
            del result[start:end]
            return result
        except Exception:
            return list(lines_list)

    return {
        "read_file": read_file,
        "write_file": write_file,
        "lines": lines,
        "search_code": search_code,
        "grep": grep,
        "insert_at": insert_at,
        "delete_lines": delete_lines,
    }

_DISABLED_MSG = "Python REPL feature is disabled. Set OMG_PYTHON_REPL_ENABLED=true"


# --- Session storage ---

_sessions: Dict[str, Dict[str, Any]] = {}
_STATE_DIR = ".omg/state/repl_sessions"


def _now_iso() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _persist_session(session_id: str) -> None:
    """Persist session metadata to disk (best-effort)."""
    if session_id not in _sessions:
        return
    _ensure_imports()
    if _atomic_json_write is None:
        return
    session = _sessions[session_id]
    meta = {
        "session_id": session["session_id"],
        "created_at": session["created_at"],
        "last_used": session["last_used"],
        "exec_count": session["exec_count"],
        "backend": session.get("backend", "stdlib"),
    }
    path = os.path.join(_STATE_DIR, f"{session_id}.json")
    try:
        _atomic_json_write(path, meta)
    except Exception:
        pass  # best-effort


def _session_info(session: Dict[str, Any]) -> Dict[str, Any]:
    """Extract public session info (no internal _backend key)."""
    return {
        "session_id": session["session_id"],
        "created_at": session["created_at"],
        "last_used": session["last_used"],
        "exec_count": session["exec_count"],
        "backend": session.get("backend", "stdlib"),
    }


# --- IPython Kernel Backend ---

class _IPythonSession:
    """Wraps a jupyter_client kernel for code execution."""

    def __init__(self):
        km, kc = _jupyter_client.manager.start_new_kernel(kernel_name="python3")
        self.kernel_manager = km
        self.kernel_client = kc
        self.kernel_client.start_channels()
        self.kernel_client.wait_for_ready(timeout=30)

    def execute(self, code_str: str) -> Dict[str, Any]:
        """Execute code on the IPython kernel and collect output."""
        msg_id = self.kernel_client.execute(code_str)
        stdout_parts: List[str] = []
        stderr_parts: List[str] = []
        result = None
        error = None

        while True:
            try:
                msg = self.kernel_client.get_iopub_msg(timeout=30)
            except Exception:
                break
            if msg["parent_header"].get("msg_id") != msg_id:
                continue
            msg_type = msg["msg_type"]
            content = msg["content"]
            if msg_type == "stream":
                if content["name"] == "stdout":
                    stdout_parts.append(content["text"])
                elif content["name"] == "stderr":
                    stderr_parts.append(content["text"])
            elif msg_type in ("execute_result", "display_data"):
                result = content["data"].get("text/plain", "")
            elif msg_type == "error":
                tb = content.get("traceback", [content.get("evalue", "")])
                error = "\n".join(tb)
            elif msg_type == "status" and content.get("execution_state") == "idle":
                break

        return {
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "result": result,
            "error": error,
        }

    def stream_execute(self, code_str: str) -> Generator[Dict[str, str], None, None]:
        """Execute code on the kernel and yield output chunks."""
        msg_id = self.kernel_client.execute(code_str)
        while True:
            try:
                msg = self.kernel_client.get_iopub_msg(timeout=30)
            except Exception:
                break
            if msg["parent_header"].get("msg_id") != msg_id:
                continue
            msg_type = msg["msg_type"]
            content = msg["content"]
            if msg_type == "stream":
                yield {"type": content["name"], "data": content["text"]}
            elif msg_type in ("execute_result", "display_data"):
                yield {"type": "result", "data": content["data"].get("text/plain", "")}
            elif msg_type == "error":
                tb = content.get("traceback", [content.get("evalue", "")])
                yield {"type": "error", "data": "\n".join(tb)}
            elif msg_type == "status" and content.get("execution_state") == "idle":
                break

    def close(self):
        """Shutdown kernel and cleanup."""
        try:
            self.kernel_client.stop_channels()
        except Exception:
            pass
        try:
            self.kernel_manager.shutdown_kernel(now=True)
        except Exception:
            pass


# --- Stdlib Fallback Backend ---

class _StdlibSession:
    """Uses code.InteractiveConsole with stdout/stderr capture."""

    def __init__(self):
        self.namespace: Dict[str, Any] = {"__builtins__": __builtins__}
        self._console = code.InteractiveConsole(locals=self.namespace)

    def execute(self, code_str: str) -> Dict[str, Any]:
        """Execute code with stdout/stderr capture via contextlib."""
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        result = None
        error = None

        try:
            with contextlib.redirect_stdout(stdout_buf), \
                 contextlib.redirect_stderr(stderr_buf):
                # Try to evaluate as single expression first
                try:
                    tree = ast.parse(code_str, mode="eval")
                    compiled = compile(tree, "<repl>", "eval")
                    result_val = eval(compiled, self.namespace)  # noqa: S307
                    if result_val is not None:
                        result = repr(result_val)
                except SyntaxError:
                    # Fall back to exec for statements
                    tree = ast.parse(code_str, mode="exec")
                    compiled = compile(tree, "<repl>", "exec")
                    exec(compiled, self.namespace)  # noqa: S102
        except Exception:
            error = traceback.format_exc()

        return {
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "result": result,
            "error": error,
        }

    def stream_execute(self, code_str: str) -> Generator[Dict[str, str], None, None]:
        """Execute code and yield output chunks.

        Note: stdlib backend doesn't support true streaming —
        executes fully then yields collected output.
        """
        output = self.execute(code_str)
        if output["stdout"]:
            yield {"type": "stdout", "data": output["stdout"]}
        if output["stderr"]:
            yield {"type": "stderr", "data": output["stderr"]}
        if output["result"] is not None:
            yield {"type": "result", "data": output["result"]}
        if output["error"]:
            yield {"type": "error", "data": output["error"]}

    def close(self):
        """Cleanup namespace."""
        self.namespace.clear()


# --- Public API ---

def start_repl_session(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Start or resume a persistent REPL session.

    Args:
        session_id: Optional ID to resume an existing session.
                    If None, creates a new session with a UUID.

    Returns:
        Session info dict: {session_id, created_at, last_used, exec_count, backend}
        or {"error": "..."} if feature flag is disabled.
    """
    if not _is_enabled():
        return {"error": _DISABLED_MSG}

    # Resume existing session
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        session["last_used"] = _now_iso()
        _persist_session(session_id)
        return _session_info(session)

    # Create new session
    new_id = session_id or str(uuid.uuid4())

    # Try IPython kernel first, fall back to stdlib
    _check_jupyter()
    backend_name = "stdlib"
    backend = None

    if _HAS_JUPYTER:
        try:
            backend = _IPythonSession()
            backend_name = "ipython"
        except Exception:
            backend = _StdlibSession()
    else:
        backend = _StdlibSession()

    now = _now_iso()
    _sessions[new_id] = {
        "session_id": new_id,
        "created_at": now,
        "last_used": now,
        "exec_count": 0,
        "backend": backend_name,
        "_backend": backend,
    }

    # Inject prelude helpers if enabled
    if _get_helpers_flag():
        prelude = _build_prelude_namespace()
        if hasattr(backend, "namespace"):
            backend.namespace.update(prelude)
    _persist_session(new_id)

    return _session_info(_sessions[new_id])


def execute_code(session_id: str, code_str: str) -> Dict[str, Any]:
    """Execute code in a session.

    Args:
        session_id: Session ID from start_repl_session()
        code_str: Python code to execute

    Returns:
        {stdout, stderr, result, error, exec_count}
        or {"error": "..."} if feature flag is disabled or session not found.
    """
    if not _is_enabled():
        return {"error": _DISABLED_MSG}

    if session_id not in _sessions:
        return {"error": f"Session not found: {session_id}"}

    # Sandbox integration: if sandbox enabled, route through sandboxed executor
    if _get_sandbox_flag():
        from tools.python_sandbox import execute_sandboxed
        session = _sessions[session_id]
        backend = session.get("_backend")
        ns = backend.namespace if hasattr(backend, "namespace") else None
        output = execute_sandboxed(code_str, namespace=ns)
        session["exec_count"] += 1
        session["last_used"] = _now_iso()
        output["exec_count"] = session["exec_count"]
        _persist_session(session_id)
        return output

    session = _sessions[session_id]
    backend = session["_backend"]

    try:
        output = backend.execute(code_str)
    except Exception as e:
        output = {
            "stdout": "",
            "stderr": "",
            "result": None,
            "error": f"{type(e).__name__}: {e}",
        }

    session["exec_count"] += 1
    session["last_used"] = _now_iso()
    output["exec_count"] = session["exec_count"]

    _persist_session(session_id)
    return output


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session info by ID.

    Args:
        session_id: Session ID to look up

    Returns:
        Session info dict, None if not found,
        or {"error": "..."} if feature flag is disabled.
    """
    if not _is_enabled():
        return {"error": _DISABLED_MSG}

    if session_id not in _sessions:
        return None

    return _session_info(_sessions[session_id])


def close_session(session_id: str) -> Union[bool, Dict[str, Any]]:
    """Close and cleanup a session.

    Args:
        session_id: Session ID to close

    Returns:
        True if closed, False if not found,
        or {"error": "..."} if feature flag is disabled.
    """
    if not _is_enabled():
        return {"error": _DISABLED_MSG}

    if session_id not in _sessions:
        return False

    session = _sessions.pop(session_id)
    backend = session.get("_backend")
    if backend is not None:
        try:
            backend.close()
        except Exception:
            pass

    return True


def list_sessions() -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List all active sessions.

    Returns:
        List of session info dicts,
        or {"error": "..."} if feature flag is disabled.
    """
    if not _is_enabled():
        return {"error": _DISABLED_MSG}

    return [_session_info(s) for s in _sessions.values()]


def stream_execute(
    session_id: str, code_str: str
) -> Generator[Dict[str, str], None, None]:
    """Execute code and stream output chunks.

    Args:
        session_id: Session ID from start_repl_session()
        code_str: Python code to execute

    Yields:
        Dicts with keys: type ("stdout"|"stderr"|"result"|"error"), data (str)
    """
    if not _is_enabled():
        yield {"type": "error", "data": _DISABLED_MSG}
        return

    if session_id not in _sessions:
        yield {"type": "error", "data": f"Session not found: {session_id}"}
        return

    session = _sessions[session_id]
    backend = session["_backend"]

    try:
        for chunk in backend.stream_execute(code_str):
            yield chunk
    except Exception as e:
        yield {"type": "error", "data": f"{type(e).__name__}: {e}"}

    session["exec_count"] += 1
    session["last_used"] = _now_iso()
    _persist_session(session_id)


# --- CLI Interface ---

def _cli_main():
    """CLI entry point for python_repl.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OMG Python REPL Tool — persistent sessions with IPython or stdlib",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--exec", dest="code", help="Execute Python code")
    parser.add_argument("--session-id", dest="session_id", help="Session ID to use")
    parser.add_argument(
        "--list-sessions", action="store_true", help="List active sessions"
    )
    parser.add_argument(
        "--close-session", dest="close_id", help="Close a session by ID"
    )
    parser.add_argument(
        "--stream", action="store_true", help="Stream output (with --exec)"
    )

    args = parser.parse_args()

    if args.list_sessions:
        result = list_sessions()
        print(json.dumps(result, indent=2))
        return

    if args.close_id:
        result = close_session(args.close_id)
        print(json.dumps({"closed": result}))
        return

    if args.code:
        session = start_repl_session(session_id=args.session_id)
        if "error" in session:
            print(json.dumps(session))
            sys.exit(1)

        sid = session["session_id"]

        if args.stream:
            for chunk in stream_execute(sid, args.code):
                print(json.dumps(chunk))
        else:
            result = execute_code(sid, args.code)
            print(json.dumps(result, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
