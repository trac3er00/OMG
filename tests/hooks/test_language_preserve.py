from __future__ import annotations
import json
import pytest
import sys
import os
import tempfile
from pathlib import Path


def test_detect_language_accessible():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from runtime.language_pipeline import detect_language

    result = detect_language("로그인 페이지를 만들어줘")
    assert result.language == "korean"


def test_cached_language_roundtrip(tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    cache_dir = tmp_path / ".omg" / "state"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "user-language.json"
    cache_file.write_text(
        json.dumps({"language": "korean", "updated_at": "2026-04-06T00:00:00Z"})
    )

    data = json.loads(cache_file.read_text())
    assert data["language"] == "korean"


def test_hook_script_callable():
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            os.path.join(
                os.path.dirname(__file__), "..", "..", "hooks", "language-preserve.py"
            ),
        ],
        input=json.dumps({"toolInput": {}, "toolResult": ""}),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
