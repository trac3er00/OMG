"""Repo-aware change classification for routing and policy attachment."""
from __future__ import annotations

import json
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

    result = {
        "schema": "DeltaClassification",
        "project_dir": project_dir,
        "goal": goal,
        "categories": sorted(categories),
        "touched_files": files,
        "manifests": manifest_names,
    }
    return result


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
