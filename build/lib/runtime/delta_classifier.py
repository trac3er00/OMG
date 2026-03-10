"""Repo-aware change classification for routing and policy attachment."""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any


_CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "auth": ("auth", "token", "secret", "login", "credential"),
    "payment": ("payment", "billing", "invoice", "stripe", "checkout"),
    "db": ("migration", "schema", "database", "sql", "postgres", "mysql"),
    "infra": ("terraform", ".tf", "deploy", "helm", "k8s", "docker"),
    "api": ("openapi", "swagger", "postman", "endpoint", "api"),
    "data": ("dataset", "lineage", "privacy", "warehouse", "etl"),
    "compliance": ("gdpr", "hipaa", "pci", "soc2", "privacy"),
    "robotics": ("robot", "actuator", "sensor", "simulator"),
    "vision": ("vision", "image", "camera", "cv"),
    "health": ("health", "patient", "clinical", "medical"),
    "algorithms": ("algorithm", "benchmark", "determinism", "complexity"),
}

_DOCS_SUFFIXES: tuple[str, ...] = (
    ".md",
    ".mdx",
    ".rst",
    ".txt",
)

_DOCS_PATH_HINTS: tuple[str, ...] = (
    "docs/",
    "readme",
    "changelog",
)

_SECURITY_CATEGORY_HINTS: tuple[str, ...] = (
    "auth",
    "payment",
    "db",
    "infra",
    "compliance",
    "health",
)

_SECURITY_TOKENS: tuple[str, ...] = (
    "security",
    "secret",
    "vulnerability",
    "audit",
    "hardening",
)

_RELEASE_TOKENS: tuple[str, ...] = (
    "release",
    "publish",
    "ship",
    "cut tag",
    "version bump",
)

_FORGE_TOKENS: tuple[str, ...] = (
    "forge",
    "prototype",
    "evaluation run",
    "lab job",
)


def classify_project_changes(
    project_dir: str,
    *,
    touched_files: list[str] | None = None,
    goal: str = "",
) -> dict[str, Any]:
    files = touched_files if touched_files is not None else _discover_files(project_dir)
    manifest_names = sorted(path.name for path in Path(project_dir).glob("*") if path.is_file())
    haystacks = [goal.lower(), *[file.lower() for file in files], *[name.lower() for name in manifest_names]]

    categories = {
        category
        for category, tokens in _CATEGORY_RULES.items()
        if any(token in haystack for token in tokens for haystack in haystacks)
    }
    if not categories:
        categories.add("implementation")

    sorted_categories = sorted(categories)
    result = {
        "schema": "DeltaClassification",
        "project_dir": project_dir,
        "goal": goal,
        "categories": sorted_categories,
        "evidence_profile": _classify_evidence_profile(goal=goal, touched_files=files, categories=sorted_categories),
        "touched_files": files,
        "manifests": manifest_names,
    }
    return result


def _classify_evidence_profile(*, goal: str, touched_files: list[str], categories: list[str]) -> str:
    lowered_goal = goal.lower()
    lowered_files = [path.lower() for path in touched_files]

    if _contains_any(lowered_goal, _RELEASE_TOKENS) or any(_contains_any(path, _RELEASE_TOKENS) for path in lowered_files):
        return "release"

    if _contains_any(lowered_goal, _FORGE_TOKENS) or any(_contains_any(path, _FORGE_TOKENS) for path in lowered_files):
        return "forge-run"

    if set(categories) & set(_SECURITY_CATEGORY_HINTS):
        return "security-audit"
    if _contains_any(lowered_goal, _SECURITY_TOKENS) or any(_contains_any(path, _SECURITY_TOKENS) for path in lowered_files):
        return "security-audit"

    if lowered_files and all(_is_docs_file(path) for path in lowered_files):
        return "docs-only"

    return "code-change"


def _is_docs_file(path: str) -> bool:
    lowered = path.lower()
    if lowered.endswith(_DOCS_SUFFIXES):
        return True
    return any(hint in lowered for hint in _DOCS_PATH_HINTS)


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(token in haystack for token in needles)


def _discover_files(project_dir: str) -> list[str]:
    root = Path(project_dir)
    git_dir = root / ".git"
    if git_dir.exists():
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if proc.returncode == 0:
            files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            if files:
                return files

    discovered: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".omg/"):
            continue
        discovered.append(rel)
        if len(discovered) >= 32:
            break
    return discovered
