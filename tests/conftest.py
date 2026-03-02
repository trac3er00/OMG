import pytest
import os
import sys
import json
import tempfile
import shutil
import io

# Add hooks/ to sys.path for all tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hooks'))


@pytest.fixture
def tmp_project(tmp_path):
    """Creates a temp project dir with .oal/state/ledger/ structure."""
    (tmp_path / '.oal' / 'state' / 'ledger').mkdir(parents=True)
    (tmp_path / '.oal' / 'knowledge').mkdir(parents=True)
    os.environ['CLAUDE_PROJECT_DIR'] = str(tmp_path)
    yield tmp_path
    os.environ.pop('CLAUDE_PROJECT_DIR', None)


@pytest.fixture
def mock_stdin(monkeypatch):
    """Returns a function that patches sys.stdin with JSON data."""
    def _mock(data):
        monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(json.dumps(data).encode())))
    return _mock


@pytest.fixture
def clean_env(monkeypatch):
    """Clears all OAL_ env vars."""
    for key in list(os.environ.keys()):
        if key.startswith('OAL_'):
            monkeypatch.delenv(key, raising=False)
