#!/usr/bin/env python3
"""SessionEnd Hook — Captures memory + learnings after session completes.

This hook fires AFTER the session ends (fire-and-forget, no blocking capability).
Features are implemented in later tasks:
- Memory capture: Task 19
- Compound learning: Task 30
"""
import sys
import os
import json
from datetime import datetime
from typing import Callable, cast

sys.path.insert(0, os.path.dirname(__file__))
from _common import setup_crash_handler as _setup_crash_handler
from _common import json_input as _json_input
from _common import get_feature_flag as _get_feature_flag
from _common import log_hook_error as _log_hook_error

setup_crash_handler = cast(Callable[[str, bool], None], _setup_crash_handler)
json_input = cast(Callable[[], dict[str, str]], _json_input)
get_feature_flag = cast(Callable[[str], bool], _get_feature_flag)
log_hook_error = cast(Callable[[str, str], None], _log_hook_error)

setup_crash_handler('session-end-capture', False)

data = json_input()
session_id = data.get('session_id', 'unknown')
cwd = data.get('cwd', os.getcwd())

# Capture A: Memory (implemented in Task 19)
if get_feature_flag('memory'):
    try:
        from _memory import save_memory, rotate_memories

        summary_parts = [f"# Session: {datetime.now().strftime('%Y-%m-%d')} ({session_id[:8]})"]

        ledger_path = os.path.join(cwd, '.oal', 'state', 'ledger', 'tool-ledger.jsonl')
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

        checklist_path = os.path.join(cwd, '.oal', 'state', '_checklist.md')
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
            ledger_path = os.path.join(project_dir, '.oal', 'state', 'ledger', 'tool-ledger.jsonl')
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
            learn_dir = os.path.join(project_dir, '.oal', 'state', 'learnings')
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

sys.exit(0)
