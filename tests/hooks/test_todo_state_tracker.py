from __future__ import annotations

import json
from pathlib import Path

from tests.hooks.helpers import run_hook_json


def test_parses_todos_from_block_content(tmp_path: Path) -> None:
    payload = {
        "response": {
            "content": [
                {"type": "text", "text": "- [ ] first task"},
                {"type": "text", "text": "- [x] done task"},
            ]
        },
        "session_id": "session-todo",
    }

    out = run_hook_json(
        "hooks/todo-state-tracker.py",
        payload,
        env_overrides={
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "OMG_TODO_TRACKING_ENABLED": "1",
        },
    )
    assert out is None

    state_path = tmp_path / ".omg" / "state" / "todo_progress.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "first task" in state.get("incomplete", [])
    assert "done task" in state.get("complete", [])
