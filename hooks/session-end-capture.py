#!/usr/bin/env python3
"""SessionEnd Hook — Captures memory + learnings after session completes.

This hook fires AFTER the session ends (fire-and-forget, no blocking capability).
Features are implemented in later tasks:
- Memory capture: Task 19
- Compound learning: Task 30
"""
from __future__ import annotations

import sys
import os
import json
import glob
from datetime import datetime
from typing import Callable, cast

_HOOKS_DIR = os.path.dirname(__file__)
_PROJECT_ROOT = os.path.dirname(_HOOKS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from hooks._common import setup_crash_handler as _setup_crash_handler
from hooks._common import json_input as _json_input
from hooks._common import get_feature_flag as _get_feature_flag
from hooks._common import log_hook_error as _log_hook_error

setup_crash_handler = cast(Callable[[str, bool], None], _setup_crash_handler)
json_input = cast(Callable[[], dict[str, str]], _json_input)
get_feature_flag = cast(Callable[[str], bool], _get_feature_flag)
log_hook_error = cast(Callable[[str, str], None], _log_hook_error)

setup_crash_handler('session-end-capture', False)

_PROFILE_ARCH_REQUEST_MAX = 8
_PROFILE_TAG_MAX = 12
_PROFILE_RECENT_UPDATES_MAX = 5
_MIN_SIGNAL_CONFIDENCE = 0.7


def _read_json_file(path: str) -> dict[str, object]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as file_obj:
            payload = json.load(file_obj)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _read_recent_failure_entries(project_dir: str, limit: int = 20) -> list[dict[str, object]]:
    ledger_dir = os.path.join(project_dir, ".omg", "state", "ledger")
    if not os.path.exists(ledger_dir):
        return []

    entries: list[dict[str, object]] = []
    try:
        failure_files = sorted(glob.glob(os.path.join(ledger_dir, "failure-*.jsonl")))
    except OSError:
        return []

    for file_path in failure_files[-5:]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as file_obj:
                for line in file_obj:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        payload = json.loads(text)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if isinstance(payload, dict):
                        entries.append(cast(dict[str, object], payload))
        except OSError:
            continue
    return entries[-limit:]


def _normalize_tag_token(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "_")
    return "".join(ch for ch in lowered if ch.isalnum() or ch in ("_", "-"))


def _normalize_constraint_key(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "_")
    return "".join(ch for ch in lowered if ch.isalnum() or ch == "_")


def _normalize_constraint_value(value: object) -> str | int | float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if value is None:
        return None
    text = " ".join(str(value).strip().split()).lower()
    return text if text else None


def _ensure_profile_baseline(profile: dict[str, object]) -> None:
    preferences_obj = profile.get("preferences")
    preferences = preferences_obj if isinstance(preferences_obj, dict) else {}
    arch_obj = preferences.get("architecture_requests")
    preferences["architecture_requests"] = arch_obj if isinstance(arch_obj, list) else []
    constraints_obj = preferences.get("constraints")
    preferences["constraints"] = constraints_obj if isinstance(constraints_obj, dict) else {}
    profile["preferences"] = preferences

    user_vector_obj = profile.get("user_vector")
    user_vector = user_vector_obj if isinstance(user_vector_obj, dict) else {}
    tags_obj = user_vector.get("tags")
    user_vector["tags"] = tags_obj if isinstance(tags_obj, list) else []
    profile["user_vector"] = user_vector

    provenance_obj = profile.get("profile_provenance")
    provenance = provenance_obj if isinstance(provenance_obj, dict) else {}
    updates_obj = provenance.get("recent_updates")
    provenance["recent_updates"] = updates_obj if isinstance(updates_obj, list) else []
    profile["profile_provenance"] = provenance

    try:
        from runtime.profile_io import ensure_governed_preferences
        ensure_governed_preferences(cast(dict[str, object], profile))
    except Exception:
        profile["governed_preferences"] = {"style": [], "safety": []}


def _record_provenance(
    profile: dict[str, object],
    *,
    run_id: str,
    source: str,
    field: str,
    updated_at: str,
) -> None:
    provenance = cast(dict[str, object], profile["profile_provenance"])
    raw_updates = provenance.get("recent_updates", [])
    updates = raw_updates if isinstance(raw_updates, list) else []
    updates.append(
        {
            "run_id": run_id,
            "source": source,
            "field": field,
            "updated_at": updated_at,
        }
    )
    provenance["recent_updates"] = updates[-_PROFILE_RECENT_UPDATES_MAX:]


def _signal_is_contradicted(
    signal: dict[str, object],
    council_payload: dict[str, object],
    failure_entries: list[dict[str, object]],
) -> bool:
    if bool(signal.get("contradicted") is True):
        return True

    field = str(signal.get("field", "")).strip()
    verdicts_obj = council_payload.get("verdicts")
    verdicts = verdicts_obj if isinstance(verdicts_obj, dict) else {}
    for verdict in verdicts.values():
        if not isinstance(verdict, dict):
            continue
        notes = " ".join(
            str(verdict.get(part, ""))
            for part in ("reason", "notes", "message", "detail")
        ).lower()
        if "contradict" in notes and (not field or field in notes):
            return True

    for entry in failure_entries:
        if bool(entry.get("contradicted") is True):
            entry_field = str(entry.get("field", "")).strip()
            if not entry_field or entry_field == field:
                return True
        detail = " ".join(
            str(entry.get(part, ""))
            for part in ("error", "reason", "message", "detail")
        ).lower()
        if "contradict" in detail and (not field or field in detail):
            return True
    return False


def _promote_preference_learning(project_dir: str, run_id: str) -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    try:
        from runtime.memory_store import project_preference_signals
    except Exception:
        return

    intent_gate_path = os.path.join(project_dir, ".omg", "state", "intent_gate", f"{run_id}.json")
    council_path = os.path.join(project_dir, ".omg", "state", "council_verdicts", f"{run_id}.json")
    health_path = os.path.join(project_dir, ".omg", "state", "session_health", f"{run_id}.json")
    profile_path = os.path.join(project_dir, ".omg", "state", "profile.yaml")

    intent_gate = _read_json_file(intent_gate_path)
    council_payload = _read_json_file(council_path)
    session_health = _read_json_file(health_path)
    failure_entries = _read_recent_failure_entries(project_dir)

    candidate_signals = project_preference_signals(project_dir, max_signals=12)
    if not candidate_signals:
        return

    if not os.path.exists(profile_path):
        return

    try:
        from runtime.profile_io import load_profile
        profile = cast(dict[str, object], load_profile(profile_path))
    except Exception:
        return
    if not profile:
        return
    had_governed = isinstance(profile.get("governed_preferences"), dict)
    _ensure_profile_baseline(profile)
    baseline_changed = not had_governed

    health_status = str(session_health.get("status", "")).strip().lower()
    health_action = str(session_health.get("recommended_action", "")).strip().lower()
    council_status = str(council_payload.get("status", "")).strip().lower()
    requires_clarification = bool(intent_gate.get("requires_clarification") is True)
    inferred_blocked = (
        health_status == "blocked"
        or health_action == "block"
        or council_status in ("blocked", "fail")
        or requires_clarification
    )

    inferred_counts: dict[tuple[str, str], int] = {}
    explicit_to_apply: list[dict[str, object]] = []
    inferred_to_apply: list[dict[str, object]] = []

    for signal in candidate_signals:
        confidence = signal.get("confidence", 0.0)
        try:
            signal_confidence = float(confidence)
        except (TypeError, ValueError):
            signal_confidence = 0.0
        if signal_confidence < _MIN_SIGNAL_CONFIDENCE:
            continue
        if _signal_is_contradicted(signal, council_payload, failure_entries):
            continue

        source = str(signal.get("source", "")).strip().lower()
        if source in ("explicit_user", "direct_user", "user_stated"):
            explicit_to_apply.append(signal)
            continue

        field = str(signal.get("field", "")).strip()
        value = " ".join(str(signal.get("value", "")).strip().split())
        if not field or not value:
            continue
        key = (field, value)
        inferred_counts[key] = inferred_counts.get(key, 0) + 1
        inferred_to_apply.append(signal)

    pending_writes: list[dict[str, object]] = list(explicit_to_apply)
    if not inferred_blocked:
        for signal in inferred_to_apply:
            field = str(signal.get("field", "")).strip()
            value = " ".join(str(signal.get("value", "")).strip().split())
            if inferred_counts.get((field, value), 0) >= 2:
                pending_writes.append(signal)

    if not pending_writes:
        if baseline_changed:
            try:
                from runtime.profile_io import save_profile
                save_profile(profile_path, profile)
            except Exception:
                pass
        return

    updated_at = datetime.utcnow().isoformat() + "Z"
    changed = False
    for signal in pending_writes:
        field = str(signal.get("field", "")).strip()
        value = " ".join(str(signal.get("value", "")).strip().split())
        if not field or not value:
            continue

        source = str(signal.get("source", "")).strip().lower() or "inferred_observation"
        section = str(signal.get("section", "style")).strip().lower() or "style"
        is_destructive = bool(signal.get("destructive") is True)

        if section not in ("style", "safety"):
            section = "style"

        if is_destructive:
            confirmation_state = "pending_confirmation"
        elif source in ("explicit_user", "direct_user", "user_stated"):
            confirmation_state = "confirmed"
        else:
            confirmation_state = "inferred"

        decay_metadata: dict[str, object] | None = None
        if section == "style" and confirmation_state == "inferred":
            decay_metadata = {
                "decay_score": 0.0,
                "last_seen_at": updated_at,
                "decay_reason": "inferred_signal",
            }

        try:
            from runtime.profile_io import upsert_governed_preference
            upsert_governed_preference(
                cast(dict[str, object], profile),
                field=field,
                value=value,
                source=source,
                learned_at=updated_at,
                updated_at=updated_at,
                section=section,
                confirmation_state=confirmation_state,
                decay_metadata=decay_metadata,
            )
            changed = True
        except Exception:
            pass

        if confirmation_state == "pending_confirmation":
            continue

        preferences = cast(dict[str, object], profile["preferences"])
        user_vector = cast(dict[str, object], profile["user_vector"])

        if field == "preferences.architecture_requests":
            raw_arch = preferences.get("architecture_requests", [])
            arch = raw_arch if isinstance(raw_arch, list) else []
            if value in arch:
                continue
            arch.append(value)
            preferences["architecture_requests"] = arch[-_PROFILE_ARCH_REQUEST_MAX:]
            _record_provenance(profile, run_id=run_id, source=source, field=field, updated_at=updated_at)
            changed = True
            continue

        if field.startswith("preferences.constraints."):
            constraint_key = _normalize_constraint_key(field.split("preferences.constraints.", 1)[1])
            constraint_value = _normalize_constraint_value(value)
            if not constraint_key or constraint_value is None:
                continue
            raw_constraints = preferences.get("constraints", {})
            constraints = raw_constraints if isinstance(raw_constraints, dict) else {}
            if constraints.get(constraint_key) == constraint_value:
                continue
            constraints[constraint_key] = constraint_value
            preferences["constraints"] = constraints
            _record_provenance(profile, run_id=run_id, source=source, field=field, updated_at=updated_at)
            changed = True
            continue

        if field == "user_vector.tags":
            token = _normalize_tag_token(value)
            if not token:
                continue
            raw_tags = user_vector.get("tags", [])
            tags = raw_tags if isinstance(raw_tags, list) else []
            if token in tags:
                continue
            tags.append(token)
            user_vector["tags"] = tags[-_PROFILE_TAG_MAX:]
            _record_provenance(profile, run_id=run_id, source=source, field=field, updated_at=updated_at)
            changed = True

    if not changed:
        if baseline_changed:
            try:
                from runtime.profile_io import save_profile
                save_profile(profile_path, profile)
            except Exception:
                pass
        return

    try:
        from runtime.profile_io import save_profile
        save_profile(profile_path, profile)
    except Exception:
        return

data = json_input()
session_id = data.get('session_id', 'unknown')
cwd = data.get('cwd', os.getcwd())

# Capture A: Memory (implemented in Task 19)
if get_feature_flag('memory'):
    try:
        from hooks._memory import save_memory, rotate_memories

        summary_parts = [f"# Session: {datetime.now().strftime('%Y-%m-%d')} ({session_id[:8]})"]

        ledger_path = os.path.join(cwd, '.omg', 'state', 'ledger', 'tool-ledger.jsonl')
        if os.path.exists(ledger_path):
            try:
                with open(ledger_path) as file_obj:
                    lines = file_obj.readlines()[-10:]
                tools_used: list[str] = []
                for line in lines:
                    try:
                        entry = json.loads(line.strip())
                        if not isinstance(entry, dict):
                            continue
                        tool = entry.get('tool', '')
                        fname = entry.get('file', entry.get('path', ''))
                        if tool and fname:
                            tools_used.append(f"  - {tool}: {fname}")
                        elif tool:
                            tools_used.append(f"  - {tool}")
                    except (json.JSONDecodeError, KeyError):
                        pass
                if tools_used:
                    summary_parts.append("## What Was Done")
                    summary_parts.extend(tools_used[:5])
            except OSError:
                pass

        checklist_path = os.path.join(cwd, '.omg', 'state', '_checklist.md')
        if os.path.exists(checklist_path):
            try:
                with open(checklist_path) as file_obj:
                    cl_lines = file_obj.readlines()
                total = sum(1 for line in cl_lines if '[ ]' in line or '[x]' in line)
                done = sum(1 for line in cl_lines if '[x]' in line.lower())
                if total > 0:
                    summary_parts.append(f"## Outcome\n- Checklist: {done}/{total} complete")
            except OSError:
                pass

        summary = '\n'.join(summary_parts)
        _ = save_memory(cwd, session_id, summary)
        _ = rotate_memories(cwd)
    except Exception as e:
        log_hook_error('session-end-capture', str(e))

# Capture B: Compound learning (implemented in Task 30)
if get_feature_flag('compound_learning'):
    try:
        def capture_learnings(project_dir, session_id):
            ledger_path = os.path.join(project_dir, '.omg', 'state', 'ledger', 'tool-ledger.jsonl')
            if not os.path.exists(ledger_path):
                return

            # Read last 100 entries
            entries = []
            with open(ledger_path) as f:
                for line in f:
                    try:
                        entries.append(json.loads(line.strip()))
                    except Exception:
                        pass
            entries = entries[-100:]

            if not entries:
                return  # No entries → no learning file

            # Count tool and file usage
            tool_counts = {}
            file_counts = {}
            for e in entries:
                tool = e.get('tool', 'unknown')
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
                f_path = e.get('file', e.get('path', ''))
                if f_path:
                    file_counts[f_path] = file_counts.get(f_path, 0) + 1

            # Write learning file
            date_str = datetime.now().strftime('%Y-%m-%d')
            session_short = session_id[:8] if len(session_id) > 8 else session_id
            learn_dir = os.path.join(project_dir, '.omg', 'state', 'learnings')
            os.makedirs(learn_dir, exist_ok=True)
            learn_path = os.path.join(learn_dir, f'{date_str}-{session_short}.md')

            lines = [f'# Learnings: {date_str}', '## Most Used Tools']
            for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1])[:5]:
                lines.append(f'- {tool}: {count}x')
            lines.append('## Most Modified Files')
            for fpath, count in sorted(file_counts.items(), key=lambda x: -x[1])[:5]:
                lines.append(f'- {fpath}: {count}x')

            content = '\n'.join(lines)
            # Cap at 300 chars
            content = content[:300]
            with open(learn_path, 'w') as f:
                f.write(content)

        capture_learnings(cwd, session_id)
    except Exception as e:
        log_hook_error('session-end-capture', str(e))

try:
    _promote_preference_learning(cwd, session_id)
except Exception as e:
    log_hook_error('session-end-capture', str(e))

sys.exit(0)
