#!/usr/bin/env python3
"""PreCompact Hook — OMG Standalone state preservation.

1) Snapshot key files from .omg/state (fallback .omc via migration)
2) Auto-generate handoff files in .omg/state
3) JetBrains hybrid summarization (feature-flagged: CONTEXT_MANAGER)
"""
import json
import importlib
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

try:
    from hooks.state_migration import resolve_state_file, resolve_state_dir
    from hooks._common import _resolve_project_dir, get_feature_flag
    from hooks._protected_context import collect_protected_context
except ImportError:
    _state_migration = importlib.import_module("state_migration")
    _common = importlib.import_module("_common")
    resolve_state_file = _state_migration.resolve_state_file
    resolve_state_dir = _state_migration.resolve_state_dir
    _resolve_project_dir = _common._resolve_project_dir
    get_feature_flag = _common.get_feature_flag
    try:
        _protected_ctx = importlib.import_module("_protected_context")
        collect_protected_context = _protected_ctx.collect_protected_context
    except Exception:
        collect_protected_context = None


MAX_SNAPSHOT_BYTES = int(os.environ.get("OMG_PRECOMPACT_MAX_SNAPSHOT_BYTES", "262144"))
GIT_DIFF_TIMEOUT_SEC = int(os.environ.get("OMG_PRECOMPACT_GIT_DIFF_TIMEOUT_SEC", "1"))


# ---------------------------------------------------------------------------
# Pure utility functions (importable for testing)
# ---------------------------------------------------------------------------

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
        raw = src_f.read(max_bytes)
    note = (
        f"\n\n[TRUNCATED by pre-compact: original_bytes={size}, kept_bytes={len(raw)}]"
    ).encode("utf-8")
    with open(dst_path, "wb") as dst_f:
        dst_f.write(raw)
        dst_f.write(note)
    return True


# ---------------------------------------------------------------------------
# JetBrains hybrid summarization (Dec 2025 empirical strategy)
# ---------------------------------------------------------------------------

# Regex for common source file extensions
_FILE_PATH_RE = re.compile(
    r"(?:[\w./-]+/)?[\w.-]+\."
    r"(?:py|ts|js|tsx|jsx|json|yaml|yml|md|txt|sh|toml|cfg|ini|sql|html|css|go|rs|java|rb|c|h|cpp)"
)

# Keywords indicating causal relationships / decisions
_CAUSAL_RE = re.compile(
    r"\b(?:decided|chose|because|therefore|fixed|resolved|implemented|"
    r"created|added|removed|deleted|changed|updated|refactored)\b",
    re.IGNORECASE,
)


def _extract_entities(text):
    """Extract file paths and causal decision sentences from text.

    Returns (file_paths: list[str], decisions: list[str]).
    """
    files = list(dict.fromkeys(_FILE_PATH_RE.findall(text)))  # dedupe, preserve order
    sentences = re.split(r"[.!?\n]", text)
    decisions = [
        s.strip()
        for s in sentences
        if _CAUSAL_RE.search(s) and len(s.strip()) > 5
    ]
    return files, decisions


def _summarize_batch(batch, batch_num, start_idx, end_idx):
    """Summarize a batch of turns into a single string.

    Format: "Batch N (turns X-Y): [files] [decisions]"
    """
    combined_text = " ".join(t.get("content", "") for t in batch)
    files, decisions = _extract_entities(combined_text)

    parts = [f"Batch {batch_num} (turns {start_idx}-{end_idx}):"]
    if files:
        parts.append(f"[files: {', '.join(files[:10])}]")
    if decisions:
        # Keep at most 3 decision excerpts, truncated
        excerpts = [d[:80] for d in decisions[:3]]
        parts.append(f"[decisions: {'; '.join(excerpts)}]")
    if not files and not decisions:
        parts.append("[no notable entities]")

    return " ".join(parts)


def _apply_hybrid_summarization(turns, config):
    """Apply JetBrains hybrid summarization strategy.

    Args:
        turns: List of turn dicts (index 0 = newest), each with 'role' and 'content'.
        config: Dict with keys:
            - full_turns: Number of most-recent turns to keep verbatim (default 10)
            - summarize_turns: Max turn index for summarization window (default 50)
            - batch_size: Number of turns per summary batch (default 21)

    Returns:
        Dict with:
            - full_turns: List of turn dicts kept verbatim
            - summaries: List of batch summary strings
            - discarded_count: Number of turns beyond the summarization window
    """
    full_n = config.get("full_turns", 10)
    summarize_n = config.get("summarize_turns", 50)
    batch_size = config.get("batch_size", 21)

    total = len(turns)

    if total == 0:
        return {"full_turns": [], "summaries": [], "discarded_count": 0}

    # Latest turns kept verbatim
    full_end = min(full_n, total)
    full_turns = turns[:full_end]

    # Middle range to summarize: turns[full_end:summarize_n]
    summarize_end = min(summarize_n, total)
    middle_turns = turns[full_end:summarize_end]

    # Discarded: turns[summarize_n:]
    discarded_count = max(0, total - summarize_n)

    # Batch the middle turns
    summaries = []
    if middle_turns and batch_size > 0:
        num_batches = math.ceil(len(middle_turns) / batch_size)
        for b in range(num_batches):
            batch_start = b * batch_size
            batch_end = min((b + 1) * batch_size, len(middle_turns))
            batch = middle_turns[batch_start:batch_end]

            # Absolute indices (relative to original turns list)
            abs_start = full_end + batch_start
            abs_end = full_end + batch_end - 1

            summary = _summarize_batch(batch, b + 1, abs_start, abs_end)
            summaries.append(summary)

    return {
        "full_turns": full_turns,
        "summaries": summaries,
        "discarded_count": discarded_count,
    }


def _load_context_budget_config(project_dir):
    """Load context_budget config from settings.json, with defaults."""
    defaults = {"full_turns": 10, "summarize_turns": 50, "batch_size": 21}
    try:
        settings_path = os.path.join(project_dir, "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            budget = settings.get("_omg", {}).get("context_budget", {})
            return {
                "full_turns": budget.get("full_turns", defaults["full_turns"]),
                "summarize_turns": budget.get("summarize_turns", defaults["summarize_turns"]),
                "batch_size": budget.get("batch_size", defaults["batch_size"]),
            }
    except Exception:
        pass
    return defaults


# ---------------------------------------------------------------------------
# Main hook execution (side-effects — only runs when invoked as script)
# ---------------------------------------------------------------------------

def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    project_dir = _resolve_project_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    state_dir = resolve_state_dir(project_dir, "state", "")
    snapshot_dir = os.path.join(state_dir, "snapshots", ts)

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

    # --- Protected context registry (feature-flagged under CONTEXT_MANAGER) ---
    try:
        if collect_protected_context is not None and get_feature_flag("CONTEXT_MANAGER", default=False):
            protected = collect_protected_context(project_dir, context_text=handoff)
            if protected:
                json.dump({"additionalContext": protected}, sys.stdout)
                print(f"[OMG pre-compact] Protected context injected ({len(protected)} chars)", file=sys.stderr)
    except Exception:
        pass  # crash isolation: never fail on protected context

    # --- Hybrid summarization (feature-flagged under CONTEXT_MANAGER) ---
    try:
        if get_feature_flag("CONTEXT_MANAGER", default=False):
            turns = data.get("conversation", [])
            if turns:
                config = _load_context_budget_config(project_dir)
                result = _apply_hybrid_summarization(turns, config)
                # Format as additionalContext supplement
                summary_parts = []
                if result["summaries"]:
                    summary_parts.append("## Conversation Context (Hybrid Summary)")
                    for s in result["summaries"]:
                        summary_parts.append(s)
                    if result["discarded_count"] > 0:
                        summary_parts.append(
                            f"({result['discarded_count']} oldest turns discarded — see memory/handoff)"
                        )
                    summary_text = "\n".join(summary_parts)
                    # Output as JSON if no protected context was already output
                    print(
                        f"[OMG pre-compact] Hybrid summarization: "
                        f"{len(result['full_turns'])} full, "
                        f"{len(result['summaries'])} batches, "
                        f"{result['discarded_count']} discarded",
                        file=sys.stderr,
                    )
    except Exception:
        pass  # crash isolation: never fail on hybrid summarization

    sys.exit(0)


if __name__ == "__main__":
    main()
