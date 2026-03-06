"""Optional upstream ecosystem sync and integration helpers for OMG."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from runtime.team_router import get_host_execution_matrix, get_provider_host_parity

ECOSYSTEM_SCHEMA = "OmgEcosystemCatalog"
ECOSYSTEM_CATALOG_VERSION = "1.0.0"
ECOSYSTEM_LOCK_SCHEMA = "OmgEcosystemLock"
DEFAULT_ECOSYSTEM_REPO_DIR = ".omg/ecosystem/repos"
DEFAULT_ECOSYSTEM_LOCK_PATH = ".omg/state/ecosystem-lock.json"
DEFAULT_ECOSYSTEM_PLAYBOOK_DIR = ".omg/knowledge/ecosystem"
MAX_SELECTION = 32


ECOSYSTEM_REPOS: tuple[dict[str, Any], ...] = (
    {
        "name": "omg-superpowers",
        "aliases": ("omg-superpowers",),
        "repo": "https://github.com/trac3er00/OMG.git",
        "ref": "main",
        "route": "plan",
        "category": "tdd",
        "capabilities": ("tdd", "planning", "execution"),
        "notes": "Primary source for strict red-green-refactor and plan execution discipline.",
    },
    {
        "name": "ralph-wiggum",
        "aliases": ("ralph-wiggum", "ralph wiggum", "ralph"),
        "repo": "https://github.com/anthropics/claude-code.git",
        "ref": "main",
        "sparse_path": "plugins/ralph-wiggum",
        "route": "runtime_ship",
        "category": "persistent-loop",
        "capabilities": ("persistent-mode", "completion-promises", "iteration"),
        "notes": "Provides loop-style persistent execution patterns via stop-hook based iteration.",
    },
    {
        "name": "claude-flow",
        "aliases": ("claude-flow",),
        "repo": "https://github.com/ruvnet/claude-flow.git",
        "ref": "main",
        "route": "ccg",
        "category": "orchestration",
        "capabilities": ("multi-agent", "coordination", "task-routing"),
        "notes": "Informs CCG-style orchestrated task dispatch and multi-agent coordination.",
    },
    {
        "name": "claude-mem",
        "aliases": ("claude-mem",),
        "repo": "https://github.com/thedotmack/claude-mem.git",
        "ref": "main",
        "route": "memory",
        "category": "memory",
        "capabilities": ("session-memory", "knowledge-capture", "recall"),
        "notes": "Complements OMG knowledge/state artifacts with memory-centric workflows.",
    },
    {
        "name": "memsearch",
        "aliases": ("memsearch", "memory-search"),
        "repo": "https://github.com/rjyo/memory-search.git",
        "ref": "main",
        "route": "memory",
        "category": "memory-search",
        "capabilities": ("semantic-search", "retrieval", "indexing"),
        "notes": "Adds focused memory retrieval and search patterns for long-running sessions.",
    },
    {
        "name": "beads",
        "aliases": ("beads",),
        "repo": "https://github.com/steveyegge/beads.git",
        "ref": "main",
        "route": "maintainer",
        "category": "context-engineering",
        "capabilities": ("context", "workflow", "agent-patterns"),
        "notes": "Source of context-engineering and disciplined workflow patterns.",
    },
    {
        "name": "planning-with-files",
        "aliases": ("planning-with-files", "planning with files"),
        "repo": "https://github.com/OthmanAdi/planning-with-files.git",
        "ref": "master",
        "route": "plan",
        "category": "planning",
        "capabilities": ("file-based-plans", "checklists", "handoff"),
        "notes": "Reinforces file-native planning artifacts and execution checklists.",
    },
    {
        "name": "hooks-mastery",
        "aliases": ("hooks-mastery", "hooks mastery"),
        "repo": "https://github.com/disler/claude-code-hooks-mastery.git",
        "ref": "main",
        "route": "health",
        "category": "hooks",
        "capabilities": ("hook-design", "hook-hardening", "hook-automation"),
        "notes": "Hardening references for robust, low-noise hook behavior.",
    },
    {
        "name": "compound-engineering",
        "aliases": ("compound-engineering", "compounding-engineering"),
        "repo": "https://github.com/EveryInc/compounding-engineering-plugin.git",
        "ref": "main",
        "route": "ccg",
        "category": "compound-workflows",
        "capabilities": ("iterative-improvement", "compound-results", "workflow-composition"),
        "notes": "Compound engineering workflow patterns for iterative gains over multiple passes.",
    },
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr or 'unknown error'}")
    return proc.stdout.strip()


def list_ecosystem_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    for repo in ECOSYSTEM_REPOS:
        cloned = dict(repo)
        cloned["aliases"] = list(repo.get("aliases", ()))
        cloned["capabilities"] = list(repo.get("capabilities", ()))
        repos.append(cloned)
    return repos


def resolve_ecosystem_repo(name: str) -> dict[str, Any] | None:
    if not name.strip():
        return None
    wanted = _canonical(name)
    for repo in ECOSYSTEM_REPOS:
        if wanted == _canonical(str(repo["name"])):
            return dict(repo)
        for alias in repo.get("aliases", ()):
            if wanted == _canonical(str(alias)):
                return dict(repo)
    return None


def resolve_ecosystem_selection(names: list[str] | None) -> tuple[list[dict[str, Any]], list[str]]:
    if not names:
        return list_ecosystem_repos(), []
    selected: list[dict[str, Any]] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in names[:MAX_SELECTION]:
        repo = resolve_ecosystem_repo(raw)
        if repo is None:
            unknown.append(raw)
            continue
        key = str(repo["name"])
        if key in seen:
            continue
        seen.add(key)
        selected.append(repo)
    return selected, unknown


def _read_lock(lock_path: Path) -> dict[str, Any]:
    if not lock_path.exists():
        return {}
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _clone_or_update_repo(
    *,
    repo: dict[str, Any],
    target: Path,
    update: bool,
    depth: int,
) -> dict[str, Any]:
    ref = str(repo.get("ref", "main"))
    repo_url = str(repo["repo"])
    sparse_path = str(repo.get("sparse_path", "")).strip()
    action = "cached"

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if sparse_path:
            _run_git(["clone", "--depth", str(depth), "--filter=blob:none", "--sparse", repo_url, str(target)])
            _run_git(["-C", str(target), "sparse-checkout", "set", sparse_path])
            if ref and ref != "main":
                _run_git(["-C", str(target), "checkout", ref])
        else:
            _run_git(
                [
                    "clone",
                    "--depth",
                    str(depth),
                    "--filter=blob:none",
                    "--branch",
                    ref,
                    "--single-branch",
                    repo_url,
                    str(target),
                ]
            )
        action = "cloned"
    elif update:
        _run_git(["-C", str(target), "fetch", "--depth", str(depth), "origin", ref])
        _run_git(["-C", str(target), "checkout", "-B", ref, "FETCH_HEAD"])
        action = "updated"

    commit = _run_git(["-C", str(target), "rev-parse", "HEAD"])
    branch = _run_git(["-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"])
    return {
        "name": repo["name"],
        "repo": repo_url,
        "ref": ref,
        "repo_segments": [".omg", "ecosystem", "repos", str(repo["name"])],
        "action": action,
        "commit": commit,
        "branch": branch,
        "sparse_path": sparse_path,
    }


def _write_playbook(project_dir: Path, selected: list[dict[str, Any]]) -> list[str]:
    base = project_dir / DEFAULT_ECOSYSTEM_PLAYBOOK_DIR
    base.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for repo in selected:
        path = base / f"{repo['name']}.md"
        capabilities = ", ".join(repo.get("capabilities", []))
        content = (
            f"# {repo['name']} Integration Notes\n\n"
            f"- Route: `{repo.get('route', '')}`\n"
            f"- Category: `{repo.get('category', '')}`\n"
            f"- Capabilities: {capabilities}\n"
            f"- Source: {repo.get('repo', '')}\n\n"
            f"{repo.get('notes', '').strip()}\n"
        )
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written


def sync_ecosystem_repos(
    *,
    project_dir: str,
    names: list[str] | None = None,
    update: bool = False,
    depth: int = 1,
) -> dict[str, Any]:
    root = Path(project_dir)
    selected, unknown = resolve_ecosystem_selection(names)
    repo_root = root / DEFAULT_ECOSYSTEM_REPO_DIR
    lock_path = root / DEFAULT_ECOSYSTEM_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for repo in selected:
        target = repo_root / str(repo["name"])
        try:
            synced = _clone_or_update_repo(repo=repo, target=target, update=update, depth=depth)
            synced["status"] = "ok"
            entries.append(synced)
        except Exception as exc:
            entries.append(
                {
                    "name": repo["name"],
                    "repo": repo["repo"],
                    "ref": repo.get("ref", "main"),
                    "repo_segments": [".omg", "ecosystem", "repos", str(repo["name"])],
                    "status": "error",
                    "error": str(exc),
                }
            )

    playbook_files = _write_playbook(root, selected)
    previous = _read_lock(lock_path)
    payload = {
        "schema": ECOSYSTEM_LOCK_SCHEMA,
        "catalog_schema": ECOSYSTEM_SCHEMA,
        "catalog_version": ECOSYSTEM_CATALOG_VERSION,
        "generated_at": _now(),
        "selected_count": len(selected),
        "unknown_count": len(unknown),
        "selected": [repo["name"] for repo in selected],
        "unknown": unknown,
        "entries": entries,
        "playbook_files": playbook_files,
        "previous_generated_at": previous.get("generated_at", ""),
    }
    lock_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return {
        "status": "ok",
        "schema": ECOSYSTEM_LOCK_SCHEMA,
        "catalog_version": ECOSYSTEM_CATALOG_VERSION,
        "lock_path": str(lock_path),
        "repo_dir": str(repo_root),
        "selected": payload["selected"],
        "unknown": unknown,
        "entries": entries,
        "playbook_files": playbook_files,
    }


def ecosystem_status(*, project_dir: str) -> dict[str, Any]:
    root = Path(project_dir)
    repo_root = root / DEFAULT_ECOSYSTEM_REPO_DIR
    lock_path = root / DEFAULT_ECOSYSTEM_LOCK_PATH
    lock = _read_lock(lock_path)

    repos = list_ecosystem_repos()
    statuses: list[dict[str, Any]] = []
    for repo in repos:
        target = repo_root / str(repo["name"])
        if not target.exists():
            statuses.append(
                {
                    "name": repo["name"],
                    "installed": False,
                    "repo_segments": [".omg", "ecosystem", "repos", str(repo["name"])],
                }
            )
            continue
        commit = ""
        branch = ""
        error = ""
        try:
            commit = _run_git(["-C", str(target), "rev-parse", "HEAD"])
            branch = _run_git(["-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"])
        except Exception as exc:
            error = str(exc)
        statuses.append(
            {
                "name": repo["name"],
                "installed": True,
                "repo_segments": [".omg", "ecosystem", "repos", str(repo["name"])],
                "commit": commit,
                "branch": branch,
                "error": error,
            }
        )

    return {
        "status": "ok",
        "schema": ECOSYSTEM_LOCK_SCHEMA,
        "catalog_schema": ECOSYSTEM_SCHEMA,
        "catalog_version": ECOSYSTEM_CATALOG_VERSION,
        "lock_exists": lock_path.exists(),
        "lock_generated_at": lock.get("generated_at", ""),
        "repo_dir": str(repo_root),
        "repos": statuses,
        "runtime_context": {
            "host_execution_matrix": get_host_execution_matrix(),
            "provider_host_parity": {
                provider: get_provider_host_parity(provider)
                for provider in ("claude", "codex", "gemini", "kimi")
            },
        },
    }
