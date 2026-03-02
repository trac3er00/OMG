import subprocess, json, os
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent.resolve()

def run_session_end(tmp_path, env_overrides=None):
    """Run session-end-capture.py with given cwd."""
    env = os.environ.copy()
    env['OAL_COMPOUND_LEARNING_ENABLED'] = 'true'
    env['OAL_MEMORY_ENABLED'] = 'false'  # Disable memory to isolate learning
    if env_overrides:
        env.update(env_overrides)

    input_data = json.dumps({'session_id': 'ses_test123', 'cwd': str(tmp_path)})
    result = subprocess.run(
        ['python3', 'hooks/session-end-capture.py'],
        input=input_data, capture_output=True, text=True, env=env,
        cwd=str(ROOT)
    )
    return result


def make_ledger_entry(tool, file_path=''):
    entry = {'ts': '2026-02-28T10:00:00Z', 'tool': tool}
    if file_path:
        entry['file'] = file_path
    return json.dumps(entry)


def test_learning_file_created_from_ledger(tmp_path):
    ledger_dir = tmp_path / '.oal' / 'state' / 'ledger'
    ledger_dir.mkdir(parents=True)
    ledger = ledger_dir / 'tool-ledger.jsonl'
    entries = [make_ledger_entry('Write', 'src/auth.ts')] * 5
    entries += [make_ledger_entry('Bash')] * 3
    entries += [make_ledger_entry('Read', 'src/auth.ts')] * 2
    ledger.write_text('\n'.join(entries))

    result = run_session_end(tmp_path)
    assert result.returncode == 0

    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    files = list(learn_dir.glob('*.md'))
    assert len(files) >= 1


def test_learning_file_under_300_chars(tmp_path):
    ledger_dir = tmp_path / '.oal' / 'state' / 'ledger'
    ledger_dir.mkdir(parents=True)
    ledger = ledger_dir / 'tool-ledger.jsonl'
    ledger.write_text('\n'.join([make_ledger_entry('Write', 'src/x.ts')] * 10))

    run_session_end(tmp_path)

    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    for f in learn_dir.glob('*.md'):
        assert len(f.read_text()) <= 300


def test_learning_contains_sections(tmp_path):
    ledger_dir = tmp_path / '.oal' / 'state' / 'ledger'
    ledger_dir.mkdir(parents=True)
    ledger = ledger_dir / 'tool-ledger.jsonl'
    ledger.write_text(make_ledger_entry('Write', 'src/auth.ts'))

    run_session_end(tmp_path)

    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    content = ''.join(f.read_text() for f in learn_dir.glob('*.md'))
    assert 'Most Used Tools' in content


def test_no_learning_file_for_empty_ledger(tmp_path):
    ledger_dir = tmp_path / '.oal' / 'state' / 'ledger'
    ledger_dir.mkdir(parents=True)
    # No ledger file at all

    result = run_session_end(tmp_path)
    assert result.returncode == 0

    learn_dir = tmp_path / '.oal' / 'state' / 'learnings'
    files = list(learn_dir.glob('*.md')) if learn_dir.exists() else []
    assert len(files) == 0


def test_exits_zero_always(tmp_path):
    result = run_session_end(tmp_path, {'OAL_COMPOUND_LEARNING_ENABLED': 'true'})
    assert result.returncode == 0
