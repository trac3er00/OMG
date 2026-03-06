"""Release-readiness summary for provider/runtime/git state."""
from __future__ import annotations

import subprocess
from typing import Any

from runtime.provider_bootstrap import collect_provider_status_with_options


def _git_branch(project_dir: str) -> str:
    proc = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    return proc.stdout.strip()


def _git_status_lines(project_dir: str) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    return [line.rstrip() for line in proc.stdout.splitlines() if line.strip()]


def collect_release_readiness(project_dir: str) -> dict[str, Any]:
    provider_status = collect_provider_status_with_options(
        project_dir,
        include_smoke=True,
        smoke_host_mode="claude_dispatch",
    )
    providers = provider_status.get("providers", [])
    blocked = [
        str(entry.get("provider", ""))
        for entry in providers
        if isinstance(entry, dict) and str(entry.get("parity_state", "")) == "blocked"
    ]
    native_ready = [
        str(entry.get("provider", ""))
        for entry in providers
        if isinstance(entry, dict) and bool(entry.get("native_ready"))
    ]
    blockers: list[str] = []
    for entry in providers:
        if not isinstance(entry, dict):
            continue
        provider_name = str(entry.get("provider", ""))
        for step in entry.get("local_steps", []):
            blockers.append(f"{provider_name}: {step}")
        for step in entry.get("provider_steps", []):
            blockers.append(f"{provider_name}: {step}")

    git_status = _git_status_lines(project_dir)
    return {
        "schema": "OmgReleaseReadiness",
        "status": "ok",
        "git": {
            "branch": _git_branch(project_dir),
            "dirty": bool(git_status),
            "status_lines": git_status,
        },
        "providers": {
            "blocked": blocked,
            "native_ready": native_ready,
            "matrix": provider_status,
        },
        "blockers": blockers,
        "ready_for_release": not blocked and not git_status,
    }
