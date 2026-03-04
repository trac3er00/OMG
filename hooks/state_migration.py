#!/usr/bin/env python3
"""State path resolution and legacy `.omc` -> `.omg` migration utilities."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
from typing import Any

DEFAULT_MIGRATION_REPORT = "legacy-to-omg.json"
LEGACY_MIGRATION_REPORT = "omc-to-omg.json"


def paths(project_dir: str) -> dict[str, str]:
    omg_root = os.path.join(project_dir, ".omg")
    return {
        "project": project_dir,
        "omg_root": omg_root,
        "omg_state": os.path.join(omg_root, "state"),
        "omg_knowledge": os.path.join(omg_root, "knowledge"),
        "omg_migrations": os.path.join(omg_root, "migrations"),
        "legacy_omc": os.path.join(project_dir, ".omc"),
    }


def ensure_omg_structure(project_dir: str) -> None:
    p = paths(project_dir)
    os.makedirs(p["omg_state"], exist_ok=True)
    os.makedirs(p["omg_knowledge"], exist_ok=True)
    os.makedirs(p["omg_migrations"], exist_ok=True)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _copy_file(src: str, dst: str) -> str:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        try:
            if _sha256_file(src) == _sha256_file(dst):
                return "unchanged"
        except Exception:
            pass
    shutil.copy2(src, dst)
    return "copied"


def _copy_tree(src: str, dst: str) -> dict[str, int]:
    stats = {"copied": 0, "unchanged": 0, "missing": 0, "errors": 0}
    if not os.path.isdir(src):
        stats["missing"] += 1
        return stats
    for root, _, files in os.walk(src):
        for fn in files:
            src_file = os.path.join(root, fn)
            rel = os.path.relpath(src_file, src)
            dst_file = os.path.join(dst, rel)
            try:
                status = _copy_file(src_file, dst_file)
                stats[status] += 1
            except Exception:
                stats["errors"] += 1
    return stats


MIGRATION_MAP: list[tuple[str, str, str]] = [
    ("file", "profile.yaml", "state/profile.yaml"),
    ("file", "working-memory.md", "state/working-memory.md"),
    ("file", "quality-gate.json", "state/quality-gate.json"),
    ("file", "_plan.md", "state/_plan.md"),
    ("file", "_checklist.md", "state/_checklist.md"),
    ("file", "handoff.md", "state/handoff.md"),
    ("file", "handoff-portable.md", "state/handoff-portable.md"),
    # Legacy root-level runtime files used by older OMC installs.
    ("file", "autopilot-state.json", "state/autopilot-state.json"),
    ("file", "ultrapilot-state.json", "state/ultrapilot-state.json"),
    ("file", "ralph-state.json", "state/ralph-state.json"),
    ("file", "ultrawork-state.json", "state/ultrawork-state.json"),
    ("file", "ultraqa-state.json", "state/ultraqa-state.json"),
    ("file", "team-state.json", "state/team-state.json"),
    ("file", "pipeline-state.json", "state/pipeline-state.json"),
    ("file", "swarm-state.json", "state/swarm-state.json"),
    ("file", "hud-state.json", "state/hud-state.json"),
    ("file", "hud-stdin-cache.json", "state/hud-stdin-cache.json"),
    ("file", "skill-active-state.json", "state/skill-active-state.json"),
    ("file", "subagent-tracking.json", "state/subagent-tracking.json"),
    # Migrate full runtime state for HUD + routing continuity.
    ("dir", "state", "state"),
    ("dir", "ledger", "state/ledger"),
    ("dir", "sessions", "state/sessions"),
    ("dir", "snapshots", "state/snapshots"),
    ("dir", "knowledge", "knowledge"),
]


def migrate_omc_to_omg(project_dir: str, force: bool = False) -> dict[str, Any]:
    ensure_omg_structure(project_dir)
    p = paths(project_dir)
    legacy = p["legacy_omc"]
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "project_dir": project_dir,
        "legacy_path": legacy,
        "target_path": p["omg_root"],
        "result": "ok",
        "entries": [],
    }

    if not os.path.isdir(legacy):
        report["result"] = "no_legacy"
    else:
        for kind, src_rel, dst_rel in MIGRATION_MAP:
            src = os.path.join(legacy, src_rel)
            dst = os.path.join(p["omg_root"], dst_rel)
            entry = {"kind": kind, "source": src_rel, "target": dst_rel, "status": "missing"}
            try:
                if kind == "file":
                    if os.path.isfile(src):
                        status = _copy_file(src, dst)
                        entry["status"] = status
                    else:
                        entry["status"] = "missing"
                else:
                    stats = _copy_tree(src, dst)
                    entry["status"] = "copied" if stats["copied"] else ("unchanged" if stats["unchanged"] else "missing")
                    entry["stats"] = stats
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = str(exc)
                report["result"] = "partial_error"
            report["entries"].append(entry)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(p["omg_migrations"], exist_ok=True)
    out_path = os.path.join(p["omg_migrations"], DEFAULT_MIGRATION_REPORT)
    legacy_out_path = os.path.join(p["omg_migrations"], LEGACY_MIGRATION_REPORT)

    # idempotent write: overwrite with latest summary
    for path in (out_path, legacy_out_path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=True)
    report["report_path"] = out_path
    report["legacy_report_path"] = legacy_out_path
    return report


def migrate_legacy_to_omg(project_dir: str, force: bool = False) -> dict[str, Any]:
    """Canonical migration API."""
    return migrate_omc_to_omg(project_dir, force=force)


def resolve_state_file(
    project_dir: str,
    omg_relative: str,
    legacy_relative: str | None = None,
    auto_migrate: bool = True,
) -> str:
    """Return preferred .omg file path; fallback to .omc if needed.

    - If .omg target exists, return it.
    - If not, and legacy exists, optionally run migration and return target if created.
    - If still absent, return the preferred target path.
    """
    p = paths(project_dir)
    preferred = os.path.join(p["omg_root"], omg_relative)
    if os.path.exists(preferred):
        return preferred

    legacy_rel = legacy_relative or omg_relative
    legacy_path = os.path.join(p["legacy_omc"], legacy_rel)
    if os.path.exists(legacy_path) and auto_migrate:
        migrate_legacy_to_omg(project_dir)
        if os.path.exists(preferred):
            return preferred
    if os.path.exists(legacy_path):
        return legacy_path
    return preferred


def resolve_state_dir(
    project_dir: str,
    omg_relative: str,
    legacy_relative: str | None = None,
    auto_migrate: bool = True,
) -> str:
    p = paths(project_dir)
    preferred = os.path.join(p["omg_root"], omg_relative)
    if os.path.isdir(preferred):
        return preferred

    legacy_rel = legacy_relative or omg_relative
    legacy_path = os.path.join(p["legacy_omc"], legacy_rel)
    if os.path.isdir(legacy_path) and auto_migrate:
        migrate_legacy_to_omg(project_dir)
        if os.path.isdir(preferred):
            return preferred
    if os.path.isdir(legacy_path):
        return legacy_path
    return preferred
