from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_settings_plugin_allowlist_covers_openagent_family() -> None:
    settings = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
    omg = settings.get("_omg") or {}
    plugin_allowlist = set(omg.get("plugin_allowlist") or [])

    expected = {
        "oh-my-openagent",
        "oh-my-opencode",
        "oh-my-codex",
        "oh-my-claudecode",
    }

    assert expected.issubset(plugin_allowlist)
    assert "oh-my-openagent@omg" not in plugin_allowlist
    assert "oh-my-opencode@omg" not in plugin_allowlist
