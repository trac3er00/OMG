from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = ROOT / "hooks"
SETTINGS_PATH = ROOT / "settings.json"
HOOK_PATH_RE = re.compile(r"\$HOME/\.claude/hooks/([^\"']+\.py)")


def _iter_hook_commands(payload: object) -> list[str]:
    commands: list[str] = []
    hooks = payload.get("hooks", {}) if isinstance(payload, dict) else {}
    if not isinstance(hooks, dict):
        return commands

    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            nested_hooks = entry.get("hooks", [])
            if not isinstance(nested_hooks, list):
                continue
            for hook in nested_hooks:
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command")
                if isinstance(command, str):
                    commands.append(command)
    return commands


def test_settings_hook_commands_reference_shipped_hook_files() -> None:
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

    referenced = {
        match.group(1)
        for command in _iter_hook_commands(settings)
        for match in [HOOK_PATH_RE.search(command)]
        if match is not None
    }

    missing = sorted(name for name in referenced if not (HOOKS_DIR / name).exists())
    assert not missing, f"settings.json references missing hook files: {missing}"


def test_user_prompt_submit_hook_entrypoint_executes() -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "user-prompt-submit.py")],
        input=json.dumps({"user_message": "/OMG:setup"}),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )

    assert proc.returncode == 0


def test_instructions_loaded_hook_entrypoint_executes() -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "instructions-loaded.py")],
        input=json.dumps({"event": "InstructionsLoaded"}),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )

    assert proc.returncode == 0


def test_reviewed_hook_entrypoints_postpone_annotation_evaluation() -> None:
    for hook_name in ("idle-detector.py", "prompt-enhancer.py"):
        source = (HOOKS_DIR / hook_name).read_text(encoding="utf-8")
        assert (
            "from __future__ import annotations" in source
        ), f"{hook_name} must postpone annotation evaluation for Python 3.9-safe imports"
