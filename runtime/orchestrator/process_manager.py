"""Process management - zombie cleanup, orphan detection."""
from __future__ import annotations

import os
import psutil
import signal
import subprocess
import time
from typing import list


def get_process_tree(pid: int) -> list[int]:
    try:
        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
        return [p.pid for p in children] + [pid]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return [pid]


def kill_process_tree(pid: int, timeout: int = 5) -> bool:
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass

        gone, alive = psutil.wait_procs(children, timeout=timeout)
        for proc in alive:
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass

        try:
            parent.terminate()
            parent.wait(timeout=timeout)
        except psutil.TimeoutExpired:
            parent.kill()
        except psutil.NoSuchProcess:
            pass

        return True
    except psutil.NoSuchProcess:
        return True
    except Exception:
        return False


def cleanup_orphans(ppid: int | None = None, grace_seconds: int = 30) -> int:
    cleaned = 0
    current_pid = os.getpid()

    for proc in psutil.process_iter(["pid", "ppid", "status", "create_time"]):
        try:
            if proc.pid == current_pid:
                continue
            if proc.ppid() == 1 and proc.status() == psutil.STATUS_ZOMBIE:
                proc.kill()
                cleaned += 1
                continue

            if ppid and proc.ppid() == ppid:
                create_time = proc.create_time()
                age = time.time() - create_time
                if age > grace_seconds:
                    if proc.status() == psutil.STATUS_ZOMBIE:
                        proc.kill()
                        cleaned += 1
                    else:
                        try:
                            proc.terminate()
                            cleaned += 1
                        except psutil.NoSuchProcess:
                            pass

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return cleaned


def find_omg_subprocesses() -> list[dict]:
    results = []
    current_pid = os.getpid()

    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            if proc.pid == current_pid:
                continue

            cmdline = proc.cmdline() or []
            cmd_str = " ".join(cmdline)

            if "omg" in cmd_str.lower() or "python" in proc.name().lower():
                results.append({
                    "pid": proc.pid,
                    "name": proc.name(),
                    "cmdline": cmdline,
                    "create_time": proc.create_time(),
                    "status": proc.status(),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return results


def get_process_memory(pid: int) -> dict | None:
    try:
        proc = psutil.Process(pid)
        mem = proc.memory_info()
        return {
            "rss": mem.rss,
            "vms": mem.vms,
            "percent": proc.memory_percent(),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
