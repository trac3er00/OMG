from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

DEPLOY_MARKERS: tuple[tuple[str, str], ...] = (
    ("vercel", "vercel.json"),
    ("netlify", "netlify.toml"),
    ("fly", "fly.toml"),
)

DEPLOY_COMMANDS: dict[str, dict[str, Any]] = {
    "vercel": {
        "cli": "vercel",
        "args": ["deploy", "--prod", "--yes"],
        "supports_rollback": True,
    },
    "netlify": {
        "cli": "netlify",
        "args": ["deploy", "--prod"],
        "supports_rollback": False,
    },
    "fly": {
        "cli": "fly",
        "args": ["deploy", "--remote-only"],
        "supports_rollback": False,
    },
    "railway": {
        "cli": "railway",
        "args": ["up", "--detach"],
        "supports_rollback": False,
    },
}


def _project_path(project_dir: str) -> Path:
    return Path(project_dir).expanduser().resolve()


def _state_dir(project_path: Path) -> Path:
    path = project_path / ".omg"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deploy_manifest_path(project_path: Path) -> Path:
    path = _state_dir(project_path) / "deploy"
    path.mkdir(parents=True, exist_ok=True)
    return path / "latest.json"


def _monitoring_path(project_path: Path) -> Path:
    return _state_dir(project_path) / "monitoring.json"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def _load_deploy_manifest(project_path: Path) -> dict[str, Any] | None:
    return _load_json(_deploy_manifest_path(project_path))


def _write_deploy_manifest(project_path: Path, payload: dict[str, Any]) -> None:
    _write_json(_deploy_manifest_path(project_path), payload)


def _detect_deploy_target(project_path: Path) -> str:
    for target, marker in DEPLOY_MARKERS:
        if (project_path / marker).exists():
            return target
    return "railway"


def _guess_local_port(project_path: Path) -> int:
    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            package_data = {}
        scripts = package_data.get("scripts", {})
        if isinstance(scripts, dict):
            script_text = " ".join(str(value) for value in scripts.values())
            if "vite" in script_text:
                return 4173
            if "next" in script_text or "react-scripts" in script_text:
                return 3000
        return 3000

    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        contents = pyproject.read_text(encoding="utf-8", errors="ignore")
        if "fastapi" in contents or "uvicorn" in contents:
            return 8000
        if "flask" in contents:
            return 5000
    return 8000


def _derive_health_check_url(
    project_path: Path, deploy_manifest: dict[str, Any] | None
) -> str:
    deployed_url = deploy_manifest.get("url") if deploy_manifest else None
    if isinstance(deployed_url, str) and deployed_url.strip():
        parsed = urlsplit(deployed_url.strip())
        return urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))
    port = _guess_local_port(project_path)
    return f"http://localhost:{port}/health"


def _extract_url(output: str) -> str | None:
    match = re.search(r"https?://[^\s\"'`<>]+", output)
    if match is None:
        return None
    return match.group(0).rstrip("),.;")


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _read_git_commit(project_path: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=5,
    )
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def _record_deploy_manifest(project_path: Path, target: str, url: str | None) -> None:
    existing = _load_deploy_manifest(project_path)
    payload: dict[str, Any] = {
        "target": target,
        "deployedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if url:
        payload["url"] = url
    git_commit = _read_git_commit(project_path)
    if git_commit:
        payload["gitCommit"] = git_commit
    if existing:
        previous = {
            "target": existing.get("target", target),
            "deployedAt": existing.get("deployedAt", payload["deployedAt"]),
        }
        if existing.get("url"):
            previous["url"] = existing["url"]
        if existing.get("gitCommit"):
            previous["gitCommit"] = existing["gitCommit"]
        payload["previous"] = previous
    _write_deploy_manifest(project_path, payload)


def _choose_test_command(project_path: Path) -> list[str] | None:
    if (project_path / "package.json").exists() and _command_exists("bun"):
        return ["bun", "test"]
    if ((project_path / "pyproject.toml").exists() or (project_path / "tests").exists()) and _command_exists(
        "python3"
    ):
        return ["python3", "-m", "pytest", "tests"]
    return None


def _run_pre_deploy_tests(project_path: Path) -> dict[str, Any]:
    command = _choose_test_command(project_path)
    if command is None:
        return {
            "success": True,
            "status": "skipped",
            "command": [],
            "message": "No supported test runner detected.",
        }

    result = subprocess.run(
        command,
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    return {
        "success": result.returncode == 0,
        "status": "passed" if result.returncode == 0 else "failed",
        "command": command,
        "exit_code": result.returncode,
        "message": output,
    }


def _parse_timestamp(timestamp: Any) -> float | None:
    if not isinstance(timestamp, str) or not timestamp:
        return None
    try:
        return time.mktime(time.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def _collect_changed_files(project_path: Path) -> list[str]:
    changed: list[str] = []
    if (project_path / ".git").exists():
        for command in (["git", "status", "--short"], ["git", "diff", "--name-only", "HEAD"]):
            result = subprocess.run(
                command,
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                continue
            for raw_line in result.stdout.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                changed.append(line[3:].strip() if command[1] == "status" and len(line) > 3 else line)

    if changed:
        return sorted({item for item in changed if item})

    manifest = _load_deploy_manifest(project_path)
    deployed_at = _parse_timestamp(manifest.get("deployedAt") if manifest else None)
    if deployed_at is not None:
        for candidate in project_path.rglob("*"):
            if candidate.is_dir():
                continue
            if any(part in {".git", ".omg", "node_modules", "dist", "__pycache__"} for part in candidate.parts):
                continue
            if candidate.stat().st_mtime > deployed_at:
                changed.append(str(candidate.relative_to(project_path)))
        if changed:
            return sorted({item for item in changed if item})

    fallbacks = [
        "package.json",
        "pyproject.toml",
        "vercel.json",
        "netlify.toml",
        "fly.toml",
        "README.md",
    ]
    return [name for name in fallbacks if (project_path / name).exists()]


def _run_deploy(target: str, project_path: Path, dry_run: bool) -> dict[str, Any]:
    config = DEPLOY_COMMANDS[target]
    command = [config["cli"], *config["args"]]
    if dry_run:
        return {
            "success": True,
            "command": command,
            "message": f"Dry run: would execute {' '.join(command)}",
        }

    if not _command_exists(config["cli"]):
        return {
            "success": False,
            "command": command,
            "message": f"{config['cli']} CLI is not installed.",
        }

    result = subprocess.run(
        command,
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        return {
            "success": False,
            "command": command,
            "message": output or f"Deployment failed for {target}.",
        }

    url = _extract_url(output)
    _record_deploy_manifest(project_path, target, url)
    payload: dict[str, Any] = {
        "success": True,
        "command": command,
        "message": f"Deployment completed for {target}.",
    }
    if url:
        payload["url"] = url
        payload["message"] = f"Deployment completed for {target}: {url}"
    return payload


def setup_monitoring(project_dir: str) -> dict[str, Any]:
    project_path = _project_path(project_dir)
    deploy_manifest = _load_deploy_manifest(project_path)
    health_check_url = _derive_health_check_url(project_path, deploy_manifest)
    dashboard_url = health_check_url.replace("/health", "/monitoring")
    payload = {
        "project_dir": str(project_path),
        "health_check_url": health_check_url,
        "monitoring_enabled": True,
        "dashboard_url": dashboard_url,
        "configured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(_monitoring_path(project_path), payload)
    return {
        "health_check_url": health_check_url,
        "monitoring_enabled": True,
        "dashboard_url": dashboard_url,
    }


def check_health(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    request = Request(url, headers={"User-Agent": "omg-operate/3.0"}, method="GET")
    try:
        with urlopen(request, timeout=5) as response:
            status_code = getattr(response, "status", response.getcode())
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        return {
            "url": url,
            "ok": 200 <= status_code < 400,
            "status_code": status_code,
            "response_time_ms": elapsed,
        }
    except HTTPError as error:
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        return {
            "url": url,
            "ok": False,
            "status_code": error.code,
            "response_time_ms": elapsed,
            "error": str(error),
        }
    except URLError as error:
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        return {
            "url": url,
            "ok": False,
            "status_code": None,
            "response_time_ms": elapsed,
            "error": str(error.reason),
        }


def update_deployment(project_dir: str, dry_run: bool) -> dict[str, Any]:
    project_path = _project_path(project_dir)
    target = _detect_deploy_target(project_path)
    changed_files = _collect_changed_files(project_path)
    rollback_available = bool(DEPLOY_COMMANDS[target].get("supports_rollback", False))
    tests = _run_pre_deploy_tests(project_path)

    if not changed_files:
        return {
            "success": True,
            "target": target,
            "changed_files": [],
            "tests": tests,
            "rollback_available": rollback_available,
            "message": "No changed files detected. Nothing to update.",
        }

    if tests.get("status") == "failed":
        return {
            "success": False,
            "target": target,
            "changed_files": changed_files,
            "tests": tests,
            "rollback_available": rollback_available,
            "message": "Tests failed; update aborted before deploy. Rollback available: {}.".format(
                "yes" if rollback_available else "manual"
            ),
        }

    deploy_result = _run_deploy(target, project_path, dry_run)
    payload = {
        "success": bool(deploy_result.get("success", False)),
        "target": target,
        "changed_files": changed_files,
        "tests": tests,
        "rollback_available": rollback_available,
        "message": "{} Rollback available: {}.".format(
            deploy_result.get("message", "Update processed."),
            "yes" if rollback_available else "manual provider controls",
        ),
    }
    if "url" in deploy_result:
        payload["url"] = deploy_result["url"]
    return payload
