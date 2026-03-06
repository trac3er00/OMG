#!/usr/bin/env python3
"""Standalone OMG HUD/workbench for Codex."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess


SKILL_MARKER = ".omg-managed-skill"


def _default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _count_ledger_events(ledger_dir: Path) -> int:
    if not ledger_dir.exists():
        return 0
    total = 0
    for path in sorted(ledger_dir.glob("*.jsonl")):
        try:
            total += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            continue
    return total


def _git_info(project_dir: Path) -> dict[str, object]:
    try:
        inside = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"inside_worktree": False, "branch": "", "dirty": False}

    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return {"inside_worktree": False, "branch": "", "dirty": False}

    branch = ""
    dirty = False
    try:
        branch_proc = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if branch_proc.returncode == 0:
            branch = branch_proc.stdout.strip()

        status_proc = subprocess.run(
            ["git", "-C", str(project_dir), "status", "--short"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if status_proc.returncode == 0:
            dirty = bool(status_proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass

    return {"inside_worktree": True, "branch": branch, "dirty": dirty}


def _provider_state() -> dict[str, dict[str, object]]:
    return {
        name: {"available": shutil.which(name) is not None}
        for name in ("codex", "gemini", "kimi")
    }


def _codex_skill_state(codex_home: Path) -> dict[str, object]:
    skills_root = codex_home / "skills"
    all_skills: list[str] = []
    omg_skills: list[str] = []

    if skills_root.exists():
        for path in sorted(skills_root.iterdir()):
            if not path.is_dir():
                continue
            all_skills.append(path.name)
            if (path / SKILL_MARKER).exists():
                omg_skills.append(path.name)

    return {
        "home": str(codex_home),
        "skills_root": str(skills_root),
        "bin": str(codex_home / "bin" / "omg-codex-hud"),
        "hud": str(codex_home / "hud" / "omg-codex-hud.py"),
        "all_skills": all_skills,
        "omg_skills": omg_skills,
    }


def build_payload(project_dir: Path, codex_home: Path) -> dict[str, object]:
    state_dir = project_dir / ".omg" / "state"
    knowledge_dir = project_dir / ".omg" / "knowledge"

    return {
        "schema": "OmgCodexHud",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "path": str(project_dir),
            "mode": _read_text(state_dir / "mode.txt"),
            "handoff_present": (state_dir / "handoff.md").exists(),
            "notes_present": (knowledge_dir / "notes.md").exists(),
            "ledger_events": _count_ledger_events(state_dir / "ledger"),
            "git": _git_info(project_dir),
        },
        "codex": _codex_skill_state(codex_home),
        "providers": _provider_state(),
    }


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


def render_text(payload: dict[str, object]) -> str:
    project = payload["project"]
    codex = payload["codex"]
    providers = payload["providers"]
    assert isinstance(project, dict)
    assert isinstance(codex, dict)
    assert isinstance(providers, dict)

    git = project["git"]
    assert isinstance(git, dict)
    if git.get("inside_worktree"):
        dirty = "dirty" if git.get("dirty") else "clean"
        git_line = f"Git: {git.get('branch') or 'detached'} ({dirty})"
    else:
        git_line = "Git: n/a"

    omg_skills = codex.get("omg_skills") or []
    if isinstance(omg_skills, list) and omg_skills:
        skill_line = ", ".join(str(name) for name in omg_skills)
    else:
        skill_line = "none"

    provider_line = ", ".join(
        f"{name}={'ok' if bool(info.get('available')) else 'missing'}"
        for name, info in providers.items()
        if isinstance(info, dict)
    )

    mode = str(project.get("mode") or "unset")
    return "\n".join(
        [
            "OMG Codex HUD",
            f"Project: {project.get('path')}",
            git_line,
            f"Mode: {mode}",
            (
                f"Handoff: {_yes_no(bool(project.get('handoff_present')))} | "
                f"Notes: {_yes_no(bool(project.get('notes_present')))} | "
                f"Ledger events: {project.get('ledger_events')}"
            ),
            f"OMG skills: {skill_line}",
            f"Providers: {provider_line}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone OMG HUD/workbench for Codex")
    parser.add_argument("--project", default=os.getcwd(), help="Project directory to inspect")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    project_dir = Path(args.project).expanduser().resolve()
    codex_home = _default_codex_home()
    payload = build_payload(project_dir, codex_home)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
