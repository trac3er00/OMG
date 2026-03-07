from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = str(ROOT / "omg_natives")


def test_importing_omg_natives_does_not_expose_package_dir_as_top_level_module_path() -> None:
    sys.modules.pop("omg_natives", None)
    sys.path[:] = [path for path in sys.path if path != PACKAGE_DIR]

    importlib.import_module("omg_natives")

    assert PACKAGE_DIR not in sys.path
