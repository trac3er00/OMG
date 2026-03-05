"""SandboxedExecutor — subprocess-based process isolation for parallel agent jobs.

Runs agent jobs in separate Python processes via subprocess.Popen, providing
PID isolation, memory limits (Unix), timeout enforcement, and automatic
cleanup on parent exit.

Feature-gated: requires OMG_PARALLEL_DISPATCH_ENABLED=1.

Usage:
    from claude_experimental.parallel.sandbox import SandboxedExecutor

    executor = SandboxedExecutor()
    result = executor.run(
        job_fn_source='result = sum(range(100))',
        args={"key": "value"},
        timeout=30,
        memory_limit_mb=512,
    )
    # result = {"exit_code": 0, "stdout": "...", "stderr": "...",
    #           "pid": 12345, "duration_ms": 42.1}
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from typing import Any


# Schema version for result records
_SCHEMA_VERSION = 1

# Track all child processes for cleanup
_tracked_processes: list[subprocess.Popen[bytes]] = []
_cleanup_registered = False


def _register_cleanup() -> None:
    """Register atexit handler to kill all tracked child processes."""
    global _cleanup_registered
    if _cleanup_registered:
        return
    _cleanup_registered = True
    atexit.register(_cleanup_all_children)


def _cleanup_all_children() -> None:
    """Kill all tracked child processes (atexit handler)."""
    for proc in _tracked_processes:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
        except OSError:
            pass
    _tracked_processes.clear()


def _build_worker_script(
    job_fn_source: str,
    memory_limit_mb: int | None = None,
) -> str:
    """Build the Python script that runs inside the subprocess.

    The worker:
    1. Reads JSON args from stdin
    2. Optionally sets memory limits via resource.setrlimit (Unix only)
    3. Executes the job function source code
    4. Writes JSON result to stdout
    """
    escaped_source = (
        job_fn_source
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )

    lines: list[str] = [
        "import json",
        "import sys",
        "import os",
        "import traceback",
        "",
    ]

    # Optional memory limit via resource.setrlimit (Unix only)
    if memory_limit_mb is not None and memory_limit_mb > 0:
        limit_bytes = memory_limit_mb * 1024 * 1024
        lines.extend([
            "try:",
            "    import resource",
            f"    resource.setrlimit(resource.RLIMIT_AS, ({limit_bytes}, {limit_bytes}))",
            "except (ImportError, ValueError, OSError):",
            "    pass",
            "",
        ])

    lines.extend([
        "def _run():",
        "    args_raw = sys.stdin.read()",
        "    try:",
        "        args = json.loads(args_raw) if args_raw.strip() else {}",
        "    except json.JSONDecodeError:",
        "        args = {}",
        "",
        "    result = None",
        "    error = None",
        "    try:",
        f"        _locals = {{'args': args, 'result': None}}",
        f"        exec('{escaped_source}', {{}}, _locals)",
        "        result = _locals.get('result')",
        "    except Exception:",
        "        error = traceback.format_exc()",
        "",
        "    output = {",
        f"        'schema_version': {_SCHEMA_VERSION},",
        "        'pid': os.getpid(),",
        "        'result': result,",
        "        'error': error,",
        "    }",
        "    sys.stdout.write(json.dumps(output))",
        "    sys.stdout.flush()",
        "",
        "_run()",
    ])

    return "\n".join(lines)


class SandboxedExecutor:
    """Runs agent jobs in isolated subprocess sandboxes.

    Each job runs in a separate Python process with:
    - PID isolation (separate process, not forked)
    - Optional memory limits via resource.setrlimit (Unix)
    - Timeout enforcement via subprocess timeout
    - Automatic cleanup of child processes on parent exit

    Integrates as optional isolation backend in ParallelExecutor
    via isolation="process".
    """

    def __init__(self, python_executable: str | None = None) -> None:
        """Initialize SandboxedExecutor.

        Args:
            python_executable: Path to Python interpreter. Defaults to sys.executable.
                Uses explicit executable path (spawn semantics, NOT fork).
        """
        from claude_experimental.parallel import _require_enabled
        _require_enabled()

        self.python_executable = python_executable or sys.executable
        _register_cleanup()

    def run(
        self,
        job_fn_source: str,
        args: dict[str, Any] | None = None,
        timeout: int = 30,
        memory_limit_mb: int = 512,
    ) -> dict[str, Any]:
        """Run a job in an isolated subprocess.

        Args:
            job_fn_source: Python source code to execute. Can reference 'args'
                dict and set 'result' variable for return value.
            args: JSON-serializable arguments passed to the job via stdin.
            timeout: Maximum execution time in seconds.
            memory_limit_mb: Memory limit in MB (Unix only, via RLIMIT_AS).
                Set to 0 to disable.

        Returns:
            dict with keys:
                - exit_code: int (0=success, non-zero=failure)
                - stdout: str (raw stdout from process)
                - stderr: str (raw stderr from process)
                - pid: int (child process PID)
                - duration_ms: float (wall-clock time in milliseconds)
                - schema_version: int (result schema version)
                - result: Any (parsed result from job, if available)
                - error: str | None (traceback if job raised exception)
        """
        worker_script = _build_worker_script(
            job_fn_source=job_fn_source,
            memory_limit_mb=memory_limit_mb if memory_limit_mb > 0 else None,
        )
        args_json = json.dumps(args or {})

        start_time = time.monotonic()
        proc: subprocess.Popen[bytes] | None = None

        try:
            # Use explicit Python executable (spawn, not fork)
            proc = subprocess.Popen(
                [self.python_executable, "-c", worker_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Prevent child from inheriting parent's signal handlers
                start_new_session=True,
            )
            _tracked_processes.append(proc)
            child_pid = proc.pid

            # Send args via stdin, then close to signal EOF
            stdout_bytes, stderr_bytes = proc.communicate(
                input=args_json.encode("utf-8"),
                timeout=timeout,
            )
            exit_code = proc.returncode
            duration_ms = (time.monotonic() - start_time) * 1000

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            # Parse structured output from worker
            parsed_result = None
            parsed_error = None
            try:
                worker_output = json.loads(stdout_str)
                parsed_result = worker_output.get("result")
                parsed_error = worker_output.get("error")
            except (json.JSONDecodeError, TypeError):
                pass

            # Worker catches exceptions and reports them in JSON while exiting 0.
            # Reflect that as a non-zero exit_code so callers keying off exit_code
            # see failures correctly.
            if parsed_error is not None and exit_code == 0:
                exit_code = 1

            return {
                "schema_version": _SCHEMA_VERSION,
                "exit_code": exit_code,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "pid": child_pid,
                "duration_ms": round(duration_ms, 2),
                "result": parsed_result,
                "error": parsed_error,
            }

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - start_time) * 1000
            child_pid = proc.pid if proc else -1

            # Force-kill the timed-out process
            if proc is not None:
                try:
                    # Send SIGTERM to process group
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    pass

            return {
                "schema_version": _SCHEMA_VERSION,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Process timed out after {timeout}s",
                "pid": child_pid,
                "duration_ms": round(duration_ms, 2),
                "result": None,
                "error": f"TimeoutError: job exceeded {timeout}s limit",
            }

        except OSError as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            return {
                "schema_version": _SCHEMA_VERSION,
                "exit_code": -2,
                "stdout": "",
                "stderr": str(e),
                "pid": -1,
                "duration_ms": round(duration_ms, 2),
                "result": None,
                "error": f"OSError: {e}",
            }

        finally:
            # Remove from tracked list if process completed
            if proc is not None and proc in _tracked_processes:
                try:
                    _tracked_processes.remove(proc)
                except ValueError:
                    pass

    def run_many(
        self,
        jobs: list[dict[str, Any]],
        max_concurrent: int = 4,
    ) -> list[dict[str, Any]]:
        """Run multiple jobs with bounded concurrency.

        Args:
            jobs: List of dicts with keys: job_fn_source, args, timeout, memory_limit_mb
            max_concurrent: Maximum number of concurrent subprocess jobs.

        Returns:
            List of result dicts in same order as input jobs.
        """
        results: list[dict[str, Any]] = []
        for job in jobs:
            result = self.run(
                job_fn_source=job.get("job_fn_source", ""),
                args=job.get("args"),
                timeout=job.get("timeout", 30),
                memory_limit_mb=job.get("memory_limit_mb", 512),
            )
            results.append(result)
        return results
