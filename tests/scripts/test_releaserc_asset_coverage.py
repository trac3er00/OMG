"""Tests that .releaserc.json git assets cover all authored surface paths.

Prevents the recurring bug where sync-release-identity.py updates a file
but semantic-release does not commit it.
"""
from __future__ import annotations

import json
import sys
from fnmatch import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from runtime.release_surfaces import get_authored_paths


class TestReleasercAssetCoverage:
    """Every file modified by sync-release-identity.py must be committed."""

    def _load_git_assets(self) -> list[str]:
        releaserc = json.loads(
            (REPO_ROOT / ".releaserc.json").read_text(encoding="utf-8")
        )
        for plugin in releaserc["plugins"]:
            if isinstance(plugin, list) and plugin[0] == "@semantic-release/git":
                return plugin[1]["assets"]
        raise AssertionError(".releaserc.json must have @semantic-release/git plugin")

    def test_all_authored_paths_covered(self) -> None:
        """Every unique authored-surface file path must match a .releaserc.json asset."""
        assets = self._load_git_assets()
        uncovered = []
        for path in get_authored_paths():
            if path in assets:
                continue
            if any(fnmatch(path, asset) for asset in assets):
                continue
            uncovered.append(path)
        assert uncovered == [], (
            f"Authored surfaces not covered by .releaserc.json assets: {uncovered}"
        )

    def test_releaserc_includes_adoption_py(self) -> None:
        """runtime/adoption.py (CANONICAL_VERSION source) must be in assets."""
        assets = self._load_git_assets()
        assert "runtime/adoption.py" in assets or any(
            fnmatch("runtime/adoption.py", a) for a in assets
        )
