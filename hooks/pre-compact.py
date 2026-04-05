#!/usr/bin/env python3
"""PreCompact Hook — OMG Standalone state preservation.

1) Snapshot key files from .omg/state (fallback .omc via migration)
2) Auto-generate handoff files in .omg/state
3) JetBrains hybrid summarization (feature-flagged: CONTEXT_MANAGER)
"""

# Performance-critical: minimal top-level imports for fast early-exit
import json
import os
import sys

# Lazy imports - loaded only when needed (see _lazy_imports())
_lazy_loaded = False
resolve_state_file = None
resolve_state_dir = None
_resolve_project_dir = None
get_feature_flag = None
collect_protected_context = None
get_model_limits = None
compaction_trigger = None


def _lazy_imports():
    """Load heavy imports only when actually needed."""
    global _lazy_loaded, resolve_state_file, resolve_state_dir
    global _resolve_project_dir, get_feature_flag, collect_protected_context
    global get_model_limits, compaction_trigger

    if _lazy_loaded:
        return
    _lazy_loaded = True

    import importlib

    try:
        from hooks.state_migration import (
            resolve_state_file as _rsf,
            resolve_state_dir as _rsd,
        )
        from hooks._common import _resolve_project_dir as _rpd, get_feature_flag as _gff
        from hooks._protected_context import collect_protected_context as _cpc

        resolve_state_file = _rsf
        resolve_state_dir = _rsd
        _resolve_project_dir = _rpd
        get_feature_flag = _gff
        collect_protected_context = _cpc
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

    try:
        from runtime.context_limits import (
            get_model_limits as _gml,
            compaction_trigger as _ct,
        )

        get_model_limits = _gml
        compaction_trigger = _ct
    except Exception:
        get_model_limits = None  # Optional: runtime.context_limits not available
        compaction_trigger = None


MAX_SNAPSHOT_BYTES = int(os.environ.get("OMG_PRECOMPACT_MAX_SNAPSHOT_BYTES", "262144"))
GIT_DIFF_TIMEOUT_SEC = int(os.environ.get("OMG_PRECOMPACT_GIT_DIFF_TIMEOUT_SEC", "1"))

# Auto-compact settings
AUTO_COMPACT_STATE_FILE = ".omg/state/auto-compact-state.json"
AUTO_COMPACT_TOOL_THRESHOLD = int(
    os.environ.get("OMG_AUTO_COMPACT_TOOL_THRESHOLD", "150")
)
AUTO_COMPACT_PHASE_CHECK_ENABLED = True  # Check for new phases by default


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


def _rotate_ledger_if_needed(ledger_path, max_lines=10000):
    """Rotate ledger file if it exceeds max_lines.

    Copies current to .bak, then writes only the last max_lines.
    """
    if not os.path.exists(ledger_path):
        return
    try:
        with open(ledger_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if len(lines) <= max_lines:
            return
        import shutil

        bak_path = ledger_path + ".bak"
        shutil.copy2(ledger_path, bak_path)
        with open(ledger_path, "w", encoding="utf-8") as f:
            f.writelines(lines[-max_lines:])
        print(
            f"[OMG pre-compact] Rotated ledger: {len(lines)} -> {max_lines} lines (backup: .bak)",
            file=sys.stderr,
        )
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to rotate ledger: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass


def snapshot_file(src_path, dst_path, max_bytes):
    import shutil  # lazy import

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

# Lazy-compiled regex patterns (compiled on first use)
_FILE_PATH_RE = None
_CAUSAL_RE = None


def _get_file_path_re():
    """Lazy-compile the file path regex."""
    global _FILE_PATH_RE
    if _FILE_PATH_RE is None:
        import re

        _FILE_PATH_RE = re.compile(
            r"(?:[\w./-]+/)?[\w.-]+\."
            r"(?:py|ts|js|tsx|jsx|json|yaml|yml|md|txt|sh|toml|cfg|ini|sql|html|css|go|rs|java|rb|c|h|cpp)"
        )
    return _FILE_PATH_RE


def _get_causal_re():
    """Lazy-compile the causal keywords regex."""
    global _CAUSAL_RE
    if _CAUSAL_RE is None:
        import re

        _CAUSAL_RE = re.compile(
            r"\b(?:decided|chose|because|therefore|fixed|resolved|implemented|"
            r"created|added|removed|deleted|changed|updated|refactored)\b",
            re.IGNORECASE,
        )
    return _CAUSAL_RE


def _extract_entities(text):
    """Extract file paths and causal decision sentences from text.

    Returns (file_paths: list[str], decisions: list[str]).
    """
    import re  # lazy import

    file_re = _get_file_path_re()
    causal_re = _get_causal_re()
    files = list(dict.fromkeys(file_re.findall(text)))  # dedupe, preserve order
    sentences = re.split(r"[.!?\n]", text)
    decisions = [
        s.strip() for s in sentences if causal_re.search(s) and len(s.strip()) > 5
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
    import math  # lazy import

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
                "summarize_turns": budget.get(
                    "summarize_turns", defaults["summarize_turns"]
                ),
                "batch_size": budget.get("batch_size", defaults["batch_size"]),
            }
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to load context budget config: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass
    return defaults


def _detect_model_id(data):
    if isinstance(data, dict):
        model = data.get("model")
        if isinstance(model, dict):
            for key in ("id", "display_name", "name"):
                value = str(model.get(key, "") or "").strip()
                if value:
                    return value
        elif isinstance(model, str) and model.strip():
            return model.strip()

        context = data.get("context")
        if isinstance(context, dict):
            nested_model = context.get("model")
            if isinstance(nested_model, dict):
                for key in ("id", "display_name", "name"):
                    value = str(nested_model.get(key, "") or "").strip()
                    if value:
                        return value
            elif isinstance(nested_model, str) and nested_model.strip():
                return nested_model.strip()

    for key in ("CLAUDE_MODEL", "OMG_MODEL_ID", "OPENAI_MODEL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value

    return ""


def _host_aware_compaction_threshold(data):
    # Ensure runtime imports are loaded for direct function calls (e.g., tests)
    _lazy_imports()
    model_id = _detect_model_id(data)
    if get_model_limits is not None and compaction_trigger is not None:
        limits = get_model_limits(model_id)
        trigger = int(compaction_trigger(model_id))
    else:
        limits = {"class_label": "128k-class"}
        trigger = 80_000
    return {
        "model_id": model_id,
        "class_label": str(limits.get("class_label", "128k-class")),
        "trigger_tokens": trigger,
    }


def _count_completed_phases(checklist_path):
    """Count completed phases (checkmarks) in the checklist.

    Returns the number of [x] or [X] markers in the checklist file.
    """
    if not os.path.exists(checklist_path):
        return 0
    try:
        with open(checklist_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.split("\n")
        completed = sum(1 for l in lines if "[x]" in l.lower())
        return completed
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to count completed phases: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass
        return 0


def _count_tool_calls_since(ledger_path, since_timestamp):
    """Count tool calls in the ledger since a given timestamp.

    Args:
        ledger_path: Path to tool-ledger.jsonl
        since_timestamp: ISO format timestamp string

    Returns:
        Number of tool calls after since_timestamp
    """
    if not os.path.exists(ledger_path):
        return 0
    try:
        from datetime import datetime  # lazy import

        cutoff = datetime.fromisoformat(since_timestamp.replace("Z", "+00:00"))
        count = 0
        with open(ledger_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if not isinstance(entry, dict):
                        continue
                    ts_str = entry.get("ts", "")
                    if not ts_str:
                        continue
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts > cutoff:
                        count += 1
                except (json.JSONDecodeError, ValueError):
                    continue
        return count
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to count tool calls since timestamp: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass
        return 0


def _load_auto_compact_state(project_dir):
    """Load auto-compact state from state file.

    Returns dict with keys: last_compact_ts, last_phase_count, tool_count_at_compact
    """
    state_path = os.path.join(project_dir, AUTO_COMPACT_STATE_FILE)
    if not os.path.exists(state_path):
        return {
            "last_compact_ts": None,
            "last_phase_count": 0,
            "tool_count_at_compact": 0,
        }
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return {
            "last_compact_ts": state.get("last_compact_ts"),
            "last_phase_count": state.get("last_phase_count", 0),
            "tool_count_at_compact": state.get("tool_count_at_compact", 0),
        }
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to load auto-compact state: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass
        return {
            "last_compact_ts": None,
            "last_phase_count": 0,
            "tool_count_at_compact": 0,
        }


def _save_auto_compact_state(project_dir, phase_count, tool_count):
    """Save auto-compact state after compaction."""
    from datetime import datetime, timezone  # lazy import

    state_path = os.path.join(project_dir, AUTO_COMPACT_STATE_FILE)
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    state = {
        "last_compact_ts": datetime.now(timezone.utc).isoformat(),
        "last_phase_count": phase_count,
        "tool_count_at_compact": tool_count,
    }
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to save auto-compact state: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass


def _check_auto_compact_advisory(project_dir):
    """Check if auto-compact should suggest compaction.

    Returns:
        tuple: (should_suggest: bool, reason: str)
    """
    state = _load_auto_compact_state(project_dir)

    # Get current counts
    from hooks.state_migration import resolve_state_file  # lazy import

    checklist_path = resolve_state_file(
        project_dir, "state/_checklist.md", "_checklist.md"
    )
    ledger_path = resolve_state_file(
        project_dir, "state/ledger/tool-ledger.jsonl", "ledger/tool-ledger.jsonl"
    )

    current_phase_count = _count_completed_phases(checklist_path)
    last_phase_count = state.get("last_phase_count", 0)

    # Check 1: New phase completed
    if AUTO_COMPACT_PHASE_CHECK_ENABLED and current_phase_count > last_phase_count:
        return (
            True,
            f"New phase completed ({current_phase_count} vs {last_phase_count})",
        )

    # Check 2: Tool call threshold exceeded
    if state.get("last_compact_ts"):
        tool_calls_since = _count_tool_calls_since(
            ledger_path, state["last_compact_ts"]
        )
        if tool_calls_since >= AUTO_COMPACT_TOOL_THRESHOLD:
            return (
                True,
                f"Tool threshold exceeded ({tool_calls_since} >= {AUTO_COMPACT_TOOL_THRESHOLD})",
            )

    return (False, "")


# ---------------------------------------------------------------------------
# Main hook execution (side-effects — only runs when invoked as script)
# ---------------------------------------------------------------------------


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Early-exit: if no .omg/ directory exists, skip all heavy work
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    omg_dir = os.path.join(project_dir, ".omg")
    state_path = os.path.join(omg_dir, "state")
    # Also check legacy .omc directory
    omc_path = os.path.join(project_dir, ".omc")
    if not os.path.isdir(state_path) and not os.path.isdir(omc_path):
        # No state to preserve - exit immediately without loading heavy imports
        sys.exit(0)

    # Load heavy imports now that we know we need them
    _lazy_imports()
    from datetime import datetime  # lazy import

    project_dir = _resolve_project_dir()
    compaction_limits = _host_aware_compaction_threshold(data)

    # Advisory: check if auto-compact heuristics suggest compaction (feature-flagged)
    if get_feature_flag("auto_compact", default=True):
        try:
            should_suggest, reason = _check_auto_compact_advisory(project_dir)
            if should_suggest:
                print(
                    f"[OMG pre-compact] Auto-compact advisory: {reason}",
                    file=sys.stderr,
                )
        except Exception:
            try:
                import sys

                print(
                    f"[omg:warn] [pre-compact] auto-compact advisory check failed: {sys.exc_info()[1]}",
                    file=sys.stderr,
                )
            except Exception:
                pass
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    state_dir = resolve_state_dir(project_dir, "state", "")
    snapshot_dir = os.path.join(state_dir, "snapshots", ts)

    snapshot_files = [
        resolve_state_file(project_dir, "state/profile.yaml", "profile.yaml"),
        resolve_state_file(project_dir, "state/working-memory.md", "working-memory.md"),
        resolve_state_file(project_dir, "state/_plan.md", "_plan.md"),
        resolve_state_file(project_dir, "state/_checklist.md", "_checklist.md"),
        resolve_state_file(project_dir, "state/quality-gate.json", "quality-gate.json"),
        resolve_state_file(
            project_dir, "state/ledger/tool-ledger.jsonl", "ledger/tool-ledger.jsonl"
        ),
        resolve_state_file(
            project_dir,
            "state/ledger/failure-tracker.json",
            "ledger/failure-tracker.json",
        ),
        resolve_state_file(project_dir, "state/ralph-loop.json", "ralph-loop.json"),
    ]
    saved = []
    for src in snapshot_files:
        if os.path.exists(src):
            dst = os.path.join(snapshot_dir, os.path.basename(src))
            if snapshot_file(src, dst, MAX_SNAPSHOT_BYTES):
                saved.append(os.path.basename(src))

    summary_files = {
        "profile": resolve_state_file(
            project_dir, "state/profile.yaml", "profile.yaml"
        ),
        "working_memory": resolve_state_file(
            project_dir, "state/working-memory.md", "working-memory.md"
        ),
        "plan": resolve_state_file(project_dir, "state/_plan.md", "_plan.md"),
        "checklist": resolve_state_file(
            project_dir, "state/_checklist.md", "_checklist.md"
        ),
        "tracker": resolve_state_file(
            project_dir,
            "state/ledger/failure-tracker.json",
            "ledger/failure-tracker.json",
        ),
        "ralph_loop": resolve_state_file(
            project_dir, "state/ralph-loop.json", "ralph-loop.json"
        ),
    }
    cached = read_cache(list(summary_files.values()))

    profile = first_lines(cached.get(summary_files["profile"]), 20)
    wm = first_lines(cached.get(summary_files["working_memory"]), 15)
    plan = first_lines(cached.get(summary_files["plan"]), 10)
    checklist = first_lines(cached.get(summary_files["checklist"]), 50)
    tracker = cached.get(summary_files["tracker"])
    ralph_loop = cached.get(summary_files["ralph_loop"])

    parts = [
        f"# Handoff -- {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "Auto-generated before context compaction.",
    ]
    model_label = compaction_limits["model_id"] or "unknown"
    parts.append(
        "## Compaction Budget\n"
        f"Model: {model_label} ({compaction_limits['class_label']})\n"
        f"Trigger: {compaction_limits['trigger_tokens']} tokens"
    )
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
            active = {
                k: v
                for k, v in t.items()
                if isinstance(v, dict) and v.get("count", 0) >= 2
            }
            if active:
                warns = [f"- {k}: {v['count']}x" for k, v in list(active.items())[:5]]
                parts.append("## Failed Approaches\n" + "\n".join(warns))
        except Exception:
            try:
                import sys

                print(
                    f"[omg:warn] [pre-compact] failed to parse failure tracker: {sys.exc_info()[1]}",
                    file=sys.stderr,
                )
            except Exception:
                pass
    if ralph_loop:
        try:
            rl = json.loads(ralph_loop)
            if rl.get("active"):
                rl_iter = rl.get("iteration", 0)
                rl_max = rl.get("max_iterations", 50)
                rl_goal = rl.get("original_prompt", "")[:80]
                parts.append(
                    f"## Ralph Loop\nIteration: {rl_iter}/{rl_max} | Goal: {rl_goal}"
                )
        except Exception:
            try:
                import sys

                print(
                    f"[omg:warn] [pre-compact] failed to parse Ralph loop state: {sys.exc_info()[1]}",
                    file=sys.stderr,
                )
            except Exception:
                pass

    try:
        import subprocess  # lazy import — security-reviewed: fixed argv, no user input, timeout-bounded

        diff_names = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            timeout=GIT_DIFF_TIMEOUT_SEC,
            cwd=project_dir,
        )
        if diff_names.returncode != 0:
            snippet = (diff_names.stderr or diff_names.stdout or "").strip()[:200]
            print(
                f"[OMG pre-compact] git diff --name-only failed "
                f"(rc={diff_names.returncode}): {snippet}",
                file=sys.stderr,
            )
            changed = []
        else:
            changed = [l for l in diff_names.stdout.strip().split("\n") if l]
        if changed:
            parts.append("## Uncommitted\n" + "\n".join(f"- {x}" for x in changed[:5]))
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to collect git diff names: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
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
    with open(
        os.path.join(state_dir, "handoff-portable.md"), "w", encoding="utf-8"
    ) as f:
        f.write(portable)

    # Keep latest 5 snapshots
    snapshots_parent = os.path.join(state_dir, "snapshots")
    try:
        if os.path.isdir(snapshots_parent):
            entries = sorted(
                [
                    d
                    for d in os.listdir(snapshots_parent)
                    if os.path.isdir(os.path.join(snapshots_parent, d))
                ]
            )
            if len(entries) > 5:
                import shutil  # lazy import

                for old in entries[:-5]:
                    shutil.rmtree(
                        os.path.join(snapshots_parent, old), ignore_errors=True
                    )
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] failed to prune old snapshots: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass

    print(
        f"[OMG pre-compact] Snapshotted {len(saved)} files -> {snapshot_dir}",
        file=sys.stderr,
    )

    # --- Auto-compact tracking (feature-flagged) ---
    try:
        if get_feature_flag("auto_compact", default=True):
            # Update state after compaction (resolve_state_file loaded by _lazy_imports)
            checklist_path = resolve_state_file(
                project_dir, "state/_checklist.md", "_checklist.md"
            )
            ledger_path = resolve_state_file(
                project_dir,
                "state/ledger/tool-ledger.jsonl",
                "ledger/tool-ledger.jsonl",
            )

            current_phase_count = _count_completed_phases(checklist_path)
            total_tool_count = 0
            if os.path.exists(ledger_path):
                with open(
                    ledger_path, "r", encoding="utf-8", errors="ignore"
                ) as _ledger_fh:
                    total_tool_count = sum(1 for _ in _ledger_fh)

            _save_auto_compact_state(project_dir, current_phase_count, total_tool_count)
            print(
                f"[OMG pre-compact] Auto-compact state saved: phase={current_phase_count}, tools={total_tool_count}",
                file=sys.stderr,
            )
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] auto-compact tracking failed: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass

    # --- Ledger rotation (prevent unbounded growth) ---
    try:
        _ledger_path = resolve_state_file(
            project_dir, "state/ledger/tool-ledger.jsonl", "ledger/tool-ledger.jsonl"
        )
        _rotate_ledger_if_needed(_ledger_path, max_lines=10000)
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] ledger rotation block failed: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass

    # --- Protected context registry (feature-flagged under CONTEXT_MANAGER) ---
    try:
        if collect_protected_context is not None and get_feature_flag(
            "CONTEXT_MANAGER", default=False
        ):
            protected = collect_protected_context(project_dir, context_text=handoff)
            if protected:
                json.dump({"additionalContext": protected}, sys.stdout)
                print(
                    f"[OMG pre-compact] Protected context injected ({len(protected)} chars)",
                    file=sys.stderr,
                )
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] protected context collection failed: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass

    # --- Hybrid summarization (feature-flagged under CONTEXT_MANAGER) ---
    try:
        if get_feature_flag("CONTEXT_MANAGER", default=False):
            turns = data.get("conversation", [])
            if turns:
                config = _load_context_budget_config(project_dir)
                result = _apply_hybrid_summarization(turns, config)
                summaries = result.get("summaries", [])
                discarded_raw = result.get("discarded_count", 0)
                discarded_count = discarded_raw if isinstance(discarded_raw, int) else 0
                full_turns = result.get("full_turns", [])
                # Format as additionalContext supplement
                summary_parts = []
                if isinstance(summaries, list) and summaries:
                    summary_parts.append("## Conversation Context (Hybrid Summary)")
                    for s in summaries:
                        if isinstance(s, str):
                            summary_parts.append(s)
                    if discarded_count > 0:
                        summary_parts.append(
                            f"({discarded_count} oldest turns discarded — see memory/handoff)"
                        )
                    _summary_text = "\n".join(summary_parts)
                    # Output as JSON if no protected context was already output
                    print(
                        f"[OMG pre-compact] Hybrid summarization: "
                        f"{len(full_turns) if isinstance(full_turns, list) else 0} full, "
                        f"{len(summaries)} batches, "
                        f"{discarded_count} discarded",
                        file=sys.stderr,
                    )
    except Exception:
        try:
            import sys

            print(
                f"[omg:warn] [pre-compact] hybrid summarization failed: {sys.exc_info()[1]}",
                file=sys.stderr,
            )
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
