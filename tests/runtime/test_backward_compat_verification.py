from __future__ import annotations

import json
import py_compile
import re
import subprocess
from pathlib import Path
from typing import cast

import pytest

from hooks import _common
from runtime.adoption import get_preset_features, resolve_preset


ROOT = Path(__file__).resolve().parents[2]
PRESET_MATRIX_PATH = ROOT / "preset-matrix.json"
UNIVERSAL_HOOK_REGISTRY_PATH = ROOT / "hooks" / "universal" / "hooks.json"
EXPECTED_PRESETS = ("safe", "balanced", "interop", "labs", "buffet", "production")
LEGACY_UNIVERSAL_ALIAS = {
    "stop.py": ROOT / "hooks" / "stop_dispatcher.py",
    "pre-tool.py": ROOT / "hooks" / "pre-tool-inject.py",
    "post-tool.py": ROOT / "hooks" / "post-tool-failure.py",
}


def _load_json_object(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)  # pyright: ignore[reportAny]
    if not isinstance(loaded, dict):
        raise AssertionError(f"expected JSON object in {path}")
    return cast(dict[str, object], loaded)


def _collect_registry_hook_filenames() -> set[str]:
    registry = _load_json_object(UNIVERSAL_HOOK_REGISTRY_PATH)

    names: set[str] = set()
    hooks_obj = registry.get("hooks", [])
    hooks = cast(list[object], hooks_obj) if isinstance(hooks_obj, list) else []
    for event in hooks:
        if not isinstance(event, dict):
            continue
        event_dict = cast(dict[str, object], event)
        nested_hooks_obj = event_dict.get("hooks", [])
        nested_hooks = (
            cast(list[object], nested_hooks_obj)
            if isinstance(nested_hooks_obj, list)
            else []
        )
        for hook in nested_hooks:
            if not isinstance(hook, dict):
                continue
            hook_dict = cast(dict[str, object], hook)
            command = hook_dict.get("command")
            if not isinstance(command, str):
                continue
            match = re.search(r"([A-Za-z0-9_\-]+\.py)", command)
            if match:
                names.add(match.group(1))
    return names


def _collect_hook_files() -> list[Path]:
    local_hooks = sorted(
        path for path in (ROOT / "hooks").glob("*.py") if path.name != "__init__.py"
    )
    universal_hooks = sorted((ROOT / "hooks" / "universal").glob("*.py"))
    return local_hooks + universal_hooks


def test_all_presets_load() -> None:
    matrix = _load_json_object(PRESET_MATRIX_PATH)
    presets = matrix.get("presets")
    assert isinstance(presets, dict)

    for preset in EXPECTED_PRESETS:
        assert preset in presets, f"missing preset in preset-matrix.json: {preset}"
        assert resolve_preset(preset) == preset
        features = get_preset_features(preset)
        assert isinstance(features, dict)
        assert features, f"preset {preset} loaded but returned empty features"


def test_all_hook_filenames_exist() -> None:
    hook_files = _collect_hook_files()
    assert len(hook_files) == 58, f"expected 58 hook filenames, found {len(hook_files)}"

    filenames = {path.name for path in hook_files}
    registry_filenames = _collect_registry_hook_filenames()

    missing_registry_targets = {
        name
        for name in registry_filenames
        if name not in filenames
        and not LEGACY_UNIVERSAL_ALIAS.get(name, Path("/non-existent")).exists()
    }
    assert not missing_registry_targets, (
        "hooks/universal/hooks.json references missing hook entrypoints: "
        f"{sorted(missing_registry_targets)}"
    )

    for hook_file in hook_files:
        _ = py_compile.compile(str(hook_file), doraise=True)


@pytest.mark.slow
def test_v230_settings_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_settings = {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "permissions": {"allow": ["Read"], "deny": []},
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": '"$HOME/.claude/omg-runtime/.venv/bin/python" "$HOME/.claude/hooks/session-start.py"',
                        }
                    ]
                }
            ]
        },
        "_omg": {
            "_version": "2.3.0",
            "preset": "balanced",
            "features": {"SETUP": True, "SETUP_WIZARD": True},
        },
    }
    settings_path = tmp_path / "settings.json"
    _ = settings_path.write_text(
        json.dumps(legacy_settings, indent=2) + "\n", encoding="utf-8"
    )

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    loaded = cast(dict[str, object], _common.get_settings(force=True))
    omg_obj = loaded.get("_omg", {})
    assert isinstance(omg_obj, dict)
    omg = cast(dict[str, object], omg_obj)
    assert omg.get("_version") == "2.3.0"
    assert omg.get("preset") == "balanced"

    migrate = subprocess.run(
        ["npx", "omg", "migrate", "--from=2.3.0", "--to=3.0.0", "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert migrate.returncode == 0, migrate.stdout + migrate.stderr
