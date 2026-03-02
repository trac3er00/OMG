#!/usr/bin/env python3
"""Learnings storage utilities for OAL compound learning."""
import os
import glob
import re


def read_file_safe(path, max_bytes=4096):
    """Safely read a file, returning empty string on error."""
    try:
        with open(path, 'r') as f:
            return f.read(max_bytes)
    except (OSError, IOError):
        return ''


def aggregate_learnings(project_dir: str, max_patterns: int = 10) -> str:
    """Read all learning files, aggregate top patterns into summary.

    Returns formatted string with top tool patterns, max 500 chars.
    """
    learn_dir = os.path.join(project_dir, '.oal', 'state', 'learnings')
    if not os.path.isdir(learn_dir):
        return ''

    all_tools = {}  # tool -> total count across sessions
    all_files = {}  # file -> total count across sessions

    for fname in os.listdir(learn_dir):
        if not fname.endswith('.md'):
            continue
        content = read_file_safe(os.path.join(learn_dir, fname))
        in_tools = False
        in_files = False
        for line in content.split('\n'):
            if line.startswith('## Most Used Tools'):
                in_tools = True
                in_files = False
                continue
            if line.startswith('## Most Modified Files'):
                in_tools = False
                in_files = True
                continue
            if line.startswith('##'):
                in_tools = False
                in_files = False
                continue
            # Parse '- toolname: Nx' format
            match = re.match(r'^-\s+(.+?):\s+(\d+)x\s*$', line.strip())
            if match:
                name = match.group(1).strip()
                count = int(match.group(2))
                if in_tools:
                    all_tools[name] = all_tools.get(name, 0) + count
                elif in_files:
                    all_files[name] = all_files.get(name, 0) + count

    return format_critical_patterns(all_tools, all_files, max_patterns)


def format_critical_patterns(tools: dict, files: dict, max_patterns: int = 10) -> str:
    """Format tool and file patterns into critical-patterns summary.

    Returns string ≤500 chars.
    """
    if not tools and not files:
        return ''

    lines = ['# Critical Patterns']

    if tools:
        lines.append('## Top Tools')
        for tool, count in sorted(tools.items(), key=lambda x: -x[1])[:max_patterns]:
            lines.append(f'- {tool}: {count}x total')

    if files:
        lines.append('## Top Files')
        for fpath, count in sorted(files.items(), key=lambda x: -x[1])[:max_patterns]:
            basename = os.path.basename(fpath)
            lines.append(f'- {basename}: {count}x total')

    result = '\n'.join(lines)
    return result[:500]  # Cap at 500 chars


def rotate_learnings(project_dir: str, max_files: int = 30) -> int:
    """Delete oldest learning files if count exceeds max_files.

    Returns number of files deleted.
    """
    learn_dir = os.path.join(project_dir, '.oal', 'state', 'learnings')
    if not os.path.isdir(learn_dir):
        return 0

    files = sorted(glob.glob(os.path.join(learn_dir, '*.md')))
    excess = len(files) - max_files
    if excess <= 0:
        return 0

    for f in files[:excess]:
        try:
            os.remove(f)
        except OSError:
            pass
    return excess


def save_critical_patterns(project_dir: str) -> str:
    """Generate and save critical-patterns.md to .oal/knowledge/.

    Returns the path of the written file, or empty string on failure.
    """
    content = aggregate_learnings(project_dir)
    if not content:
        return ''

    knowledge_dir = os.path.join(project_dir, '.oal', 'knowledge')
    os.makedirs(knowledge_dir, exist_ok=True)
    path = os.path.join(knowledge_dir, 'critical-patterns.md')

    try:
        with open(path, 'w') as f:
            f.write(content)
        return path
    except OSError:
        return ''
