"""OMG wrapper around the upstream Playwright CLI."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from runtime.playwright_pack import PlaywrightPack

WhichFn = Callable[[str], str | None]
RunnerFn = Callable[..., dict[str, object]]

PLAYWRIGHT_REMEDIATION = (
    "Install Playwright CLI with `npx playwright` support or `npm install -g @playwright/cli@latest`, "
    "then install browsers and optional skills."
)


def resolve_playwright_command(*, which: WhichFn = shutil.which) -> list[str] | None:
    """Resolve the preferred upstream Playwright CLI command."""
    if which("playwright"):
        return ["playwright"]
    if which("playwright-cli"):
        return ["playwright-cli"]
    if which("npx"):
        return ["npx", "playwright"]
    return None


def ensure_playwright_cli(
    *,
    project_dir: str | Path,
    which: WhichFn = shutil.which,
) -> dict[str, Any]:
    """Report whether an upstream Playwright CLI is available."""
    command = resolve_playwright_command(which=which)
    project_root = str(Path(project_dir).resolve())
    if command is None:
        return {
            "status": "missing",
            "project_dir": project_root,
            "remediation": PLAYWRIGHT_REMEDIATION,
        }
    return {
        "status": "ready",
        "project_dir": project_root,
        "command": command,
    }


def run_browser_cli(
    *,
    goal: str,
    project_dir: str | Path,
    runner: RunnerFn,
    which: WhichFn = shutil.which,
    isolated: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the resolved Playwright CLI and normalize its artifacts into OMG evidence."""
    readiness = ensure_playwright_cli(project_dir=project_dir, which=which)
    if readiness["status"] != "ready":
        return readiness

    project_root = Path(project_dir).resolve()
    result = runner(
        command=list(readiness["command"]),
        cwd=str(project_root),
        goal=goal,
    )
    if int(result.get("returncode", 1)) != 0:
        return {
            "status": "error",
            "project_dir": str(project_root),
            "command": readiness["command"],
            "goal": goal,
            "stdout": str(result.get("stdout", "")),
            "stderr": str(result.get("stderr", "")),
        }

    pack = PlaywrightPack(project_dir=project_root, isolated=isolated)
    normalized = pack.ingest_external_artifacts(
        output_dir=output_dir or (project_root / ".omg" / "evidence" / "browser"),
        trace_path=result.get("trace_path"),
        junit_path=result.get("junit_path"),
        screenshots=result.get("screenshots"),
        metadata=dict(result.get("metadata") or {}),
    )
    return {
        "status": "success",
        "project_dir": str(project_root),
        "command": readiness["command"],
        "goal": goal,
        **normalized,
    }
