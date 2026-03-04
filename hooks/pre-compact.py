#!/usr/bin/env python3
"""PreCompact Hook — OMG Standalone state preservation.

1) Snapshot key files from .omg/state (fallback .omc via migration)
2) Auto-generate handoff files in .omg/state
"""
import json
import importlib
import os
import shutil
import subprocess
import sys
from datetime import datetime

try:
    from hooks.state_migration import resolve_state_file, resolve_state_dir
    from hooks._common import _resolve_project_dir
except ImportError:
    _state_migration = importlib.import_module("state_migration")
    _common = importlib.import_module("_common")
    resolve_state_file = _state_migration.resolve_state_file
    resolve_state_dir = _state_migration.resolve_state_dir
    _resolve_project_dir = _common._resolve_project_dir


MAX_SNAPSHOT_BYTES = int(os.environ.get("OMG_PRECOMPACT_MAX_SNAPSHOT_BYTES", "262144"))
GIT_DIFF_TIMEOUT_SEC = int(os.environ.get("OMG_PRECOMPACT_GIT_DIFF_TIMEOUT_SEC", "1"))


try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, EOFError):
    sys.exit(0)

project_dir = _resolve_project_dir()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
state_dir = resolve_state_dir(project_dir, "state", "")
snapshot_dir = os.path.join(state_dir, "snapshots", ts)


def read_file(path, max_lines=None):
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        if not content:
            return None
        if max_lines:
            return "\n".join(content.split("\n")[:max_lines])
        return content
    except Exception:
        return None


def read_cache(paths):
    cache = {}
    for path in paths:
        cache[path] = read_file(path)
    return cache


def first_lines(text, max_lines):
    if not text:
        return None
    if not max_lines:
        return text
    return "\n".join(text.splitlines()[:max_lines])


def snapshot_file(src_path, dst_path, max_bytes):
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    try:
        size = os.path.getsize(src_path)
    except OSError:
        return False

    if max_bytes <= 0 or size <= max_bytes:
        shutil.copy2(src_path, dst_path)
        return True

    with open(src_path, "rb") as src_f:
        data = src_f.read(max_bytes)
    note = (
        f"\n\n[TRUNCATED by pre-compact: original_bytes={size}, kept_bytes={len(data)}]"
    ).encode("utf-8")
    with open(dst_path, "wb") as dst_f:
        dst_f.write(data)
        dst_f.write(note)
    return True


snapshot_files = [
    resolve_state_file(project_dir, "state/profile.yaml", "profile.yaml"),
    resolve_state_file(project_dir, "state/working-memory.md", "working-memory.md"),
    resolve_state_file(project_dir, "state/_plan.md", "_plan.md"),
    resolve_state_file(project_dir, "state/_checklist.md", "_checklist.md"),
    resolve_state_file(project_dir, "state/quality-gate.json", "quality-gate.json"),
    resolve_state_file(project_dir, "state/ledger/tool-ledger.jsonl", "ledger/tool-ledger.jsonl"),
    resolve_state_file(project_dir, "state/ledger/failure-tracker.json", "ledger/failure-tracker.json"),
    resolve_state_file(project_dir, "state/ralph-loop.json", "ralph-loop.json"),
]
cached = read_cache(snapshot_files)
saved = []
for src in snapshot_files:
    if cached.get(src) is not None:
        dst = os.path.join(snapshot_dir, os.path.basename(src))
        if snapshot_file(src, dst, MAX_SNAPSHOT_BYTES):
            saved.append(os.path.basename(src))

profile = first_lines(cached.get(resolve_state_file(project_dir, "state/profile.yaml", "profile.yaml")), 20)
wm = first_lines(cached.get(resolve_state_file(project_dir, "state/working-memory.md", "working-memory.md")), 15)
plan = first_lines(cached.get(resolve_state_file(project_dir, "state/_plan.md", "_plan.md")), 10)
checklist = first_lines(cached.get(resolve_state_file(project_dir, "state/_checklist.md", "_checklist.md")), 50)
tracker = cached.get(resolve_state_file(project_dir, "state/ledger/failure-tracker.json", "ledger/failure-tracker.json"))
ralph_loop = cached.get(resolve_state_file(project_dir, "state/ralph-loop.json", "ralph-loop.json"))

parts = [
    f"# Handoff -- {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    "Auto-generated before context compaction.",
]
if profile:
    parts.append("<!-- section: working-state -->")
    parts.append("## Project\n" + profile)
if wm:
    parts.append("## Working State\n" + wm)
if plan:
    parts.append("## Plan\n" + plan)
if checklist:
    lines = checklist.split("\n")
    done = sum(1 for l in lines if "[x]" in l.lower())
    total = sum(1 for l in lines if l.strip().startswith(("[", "- [")))
    pending = [l.strip() for l in lines if "[ ]" in l][:3]
    parts.append("<!-- section: progress -->")
    parts.append(f"## Progress: {done}/{total}")
    if pending:
        parts.append("Next:\n" + "\n".join(pending))
if tracker:
    try:
        t = json.loads(tracker)
        active = {k: v for k, v in t.items() if isinstance(v, dict) and v.get("count", 0) >= 2}
        if active:
            warns = [f"- {k}: {v['count']}x" for k, v in list(active.items())[:5]]
            parts.append("## Failed Approaches\n" + "\n".join(warns))
    except Exception:
        pass
if ralph_loop:
    try:
        rl = json.loads(ralph_loop)
        if rl.get("active"):
            rl_iter = rl.get("iteration", 0)
            rl_max = rl.get("max_iterations", 50)
            rl_goal = rl.get("original_prompt", "")[:80]
            parts.append(f"## Ralph Loop\nIteration: {rl_iter}/{rl_max} | Goal: {rl_goal}")
    except Exception:
        pass

try:
    diff_names = subprocess.run(
        ["git", "diff", "--name-only"],
        capture_output=True,
        text=True,
        timeout=GIT_DIFF_TIMEOUT_SEC,
        cwd=project_dir,
    )
    changed = [l for l in diff_names.stdout.strip().split("\n") if l]
    if changed:
        parts.append("## Uncommitted\n" + "\n".join(f"- {x}" for x in changed[:5]))
except Exception:
    pass

parts.append("## Resume Instructions")
parts.append("Read .omg/state/profile.yaml + this file.")
parts.append("\n---\n*Auto-generated before context compaction.*")
handoff = "\n\n".join(parts)
handoff_lines = handoff.split("\n")
if len(handoff_lines) > 120:
    handoff = "\n".join(handoff_lines[:120]) + "\n\n(truncated)"

os.makedirs(state_dir, exist_ok=True)
with open(os.path.join(state_dir, "handoff.md"), "w", encoding="utf-8") as f:
    f.write(handoff)

portable = handoff + "\n\nSelf-contained handoff for other platforms."
portable_lines = portable.split("\n")
if len(portable_lines) > 150:
    portable = "\n".join(portable_lines[:150]) + "\n\n(truncated)"
with open(os.path.join(state_dir, "handoff-portable.md"), "w", encoding="utf-8") as f:
    f.write(portable)

# Keep latest 5 snapshots
snapshots_parent = os.path.join(state_dir, "snapshots")
try:
    if os.path.isdir(snapshots_parent):
        entries = sorted(
            [d for d in os.listdir(snapshots_parent) if os.path.isdir(os.path.join(snapshots_parent, d))]
        )
        for old in entries[:-5]:
            shutil.rmtree(os.path.join(snapshots_parent, old), ignore_errors=True)
except Exception:
    pass

print(f"[OMG pre-compact] Snapshotted {len(saved)} files -> {snapshot_dir}", file=sys.stderr)
sys.exit(0)
