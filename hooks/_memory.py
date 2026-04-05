#!/usr/bin/env python3
import glob
import os
import sys
from datetime import datetime


def save_memory(project_dir: str, session_id: str, content: str) -> str:
    memory_dir = os.path.join(project_dir, ".omg", "state", "memory")
    os.makedirs(memory_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    session_short = session_id[:8] if len(session_id) > 8 else session_id
    filename = f"{date_str}-{session_short}.md"
    filepath = os.path.join(memory_dir, filename)
    content = content[:500]
    if os.path.exists(filepath):
        with open(filepath, "a") as file_obj:
            _ = file_obj.write("\n" + content)
    else:
        with open(filepath, "w") as file_obj:
            _ = file_obj.write(content)
    return filepath


def get_recent_memories(
    project_dir: str, max_files: int = 5, max_chars_total: int = 300
) -> str:
    memory_dir = os.path.join(project_dir, ".omg", "state", "memory")
    if not os.path.exists(memory_dir):
        return ""
    files = sorted(glob.glob(os.path.join(memory_dir, "*.md")), reverse=True)
    files = files[:max_files]
    result: list[str] = []
    total = 0
    separator = "\n---\n"
    for file_path in files:
        try:
            with open(file_path) as file_obj:
                content = file_obj.read()
            separator_len = len(separator) if result else 0
            remaining = max_chars_total - total - separator_len
            if remaining <= 0:
                break
            if len(content) > remaining:
                content = content[:remaining]
            if not content:
                break
            if result:
                total += separator_len
            result.append(content)
            total += len(content)
            if total >= max_chars_total:
                break
        except OSError:
            continue
    return separator.join(result)


def rotate_memories(project_dir: str, max_files: int = 50) -> int:
    memory_dir = os.path.join(project_dir, ".omg", "state", "memory")
    if not os.path.exists(memory_dir):
        return 0
    files = sorted(glob.glob(os.path.join(memory_dir, "*.md")))
    excess = len(files) - max_files
    if excess <= 0:
        return 0
    for file_path in files[:excess]:
        try:
            os.remove(file_path)
        except OSError:
            try:
                print(f"[omg:warn] failed to remove old memory file during rotation: {sys.exc_info()[1]}", file=sys.stderr)
            except Exception:
                pass
    return excess



def search_memories(project_dir: str, query_keywords: list[str], max_results: int = 3, max_chars: int = 200) -> str:
    """Search memory files by keyword relevance. Returns formatted excerpt string."""
    memory_dir = os.path.join(project_dir, '.omg', 'state', 'memory')
    if not os.path.isdir(memory_dir):
        return ''
    results = []
    for fname in sorted(os.listdir(memory_dir), reverse=True):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(memory_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(2048)
        except OSError:
            continue
        score = sum(1 for kw in query_keywords if kw.lower() in content.lower())
        if score > 0:
            results.append((score, fname, content))
    results.sort(key=lambda x: -x[0])
    summary_parts = []
    chars_used = 0
    for score, fname, content in results[:max_results]:
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
        excerpt = ' '.join(lines[:3])[:100]
        if chars_used + len(excerpt) > max_chars:
            break
        summary_parts.append(f'[{fname}] {excerpt}')
        chars_used += len(excerpt)
    return '\n'.join(summary_parts)
