"""Tests for hooks/_learnings.py — learnings aggregation and rotation."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks'))

from _learnings import (
    aggregate_learnings,
    format_critical_patterns,
    rotate_learnings,
    save_critical_patterns,
)


LEARNING_TEMPLATE = """# Session Learning: {session}

## Most Used Tools
- Write: {write_count}x
- Read: {read_count}x
- Bash: {bash_count}x

## Most Modified Files
- src/main.py: {file_count}x
"""


def _create_learning_file(learn_dir, name, write_count=3, read_count=2, bash_count=1, file_count=2):
    """Helper to create a properly formatted learning file."""
    content = LEARNING_TEMPLATE.format(
        session=name,
        write_count=write_count,
        read_count=read_count,
        bash_count=bash_count,
        file_count=file_count,
    )
    filepath = os.path.join(learn_dir, f'{name}.md')
    with open(filepath, 'w') as f:
        f.write(content)
    return filepath


def test_aggregate_learnings_top_tools(tmp_path):
    """Create 3 learning files with Write: 5x, 3x, 2x. Assert total ≥10x."""
    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    learn_dir.mkdir(parents=True)

    _create_learning_file(str(learn_dir), 'session-001', write_count=5, read_count=1, bash_count=1, file_count=1)
    _create_learning_file(str(learn_dir), 'session-002', write_count=3, read_count=2, bash_count=1, file_count=1)
    _create_learning_file(str(learn_dir), 'session-003', write_count=2, read_count=1, bash_count=1, file_count=1)

    result = aggregate_learnings(str(tmp_path))

    assert 'Write' in result
    assert '10x total' in result


def test_aggregate_learnings_under_500_chars(tmp_path):
    """Assert aggregated result is ≤500 chars even with many files."""
    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    learn_dir.mkdir(parents=True)

    # Create 20 learning files with varied tool names to stress the length
    for i in range(20):
        content = f"# Session Learning: session-{i:03d}\n\n"
        content += "## Most Used Tools\n"
        for j in range(10):
            content += f"- VeryLongToolName{j}ForSession{i}: {j + 1}x\n"
        content += "\n## Most Modified Files\n"
        for j in range(10):
            content += f"- src/deeply/nested/path/module{j}/component{i}.py: {j + 1}x\n"
        filepath = learn_dir / f'session-{i:03d}.md'
        filepath.write_text(content)

    result = aggregate_learnings(str(tmp_path))
    assert len(result) <= 500


def test_aggregate_learnings_empty_dir(tmp_path):
    """No learnings dir → returns empty string."""
    result = aggregate_learnings(str(tmp_path))
    assert result == ''


def test_rotate_learnings_keeps_30(tmp_path):
    """Create 35 files, rotate with max_files=30, assert 30 remain."""
    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    learn_dir.mkdir(parents=True)

    for i in range(35):
        (learn_dir / f'2026-01-{i:02d}-sess.md').write_text(f'# session {i}')

    deleted = rotate_learnings(str(tmp_path), max_files=30)

    assert deleted == 5
    remaining = list(learn_dir.glob('*.md'))
    assert len(remaining) == 30


def test_format_critical_patterns_empty():
    """Empty tools/files → returns empty string."""
    result = format_critical_patterns({}, {})
    assert result == ''


def test_save_critical_patterns(tmp_path):
    """Creates .oal/knowledge/critical-patterns.md with content."""
    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    learn_dir.mkdir(parents=True)

    _create_learning_file(str(learn_dir), 'session-001', write_count=5, read_count=3, bash_count=2, file_count=4)

    path = save_critical_patterns(str(tmp_path))

    assert path != ''
    assert os.path.exists(path)
    assert path.endswith('critical-patterns.md')

    content = open(path).read()
    assert '# Critical Patterns' in content
    assert 'Write' in content
    assert len(content) <= 500
