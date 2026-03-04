#!/usr/bin/env python3
"""Legacy wrapper for `legacy_to_omg_migrate.py`."""
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    target = Path(__file__).resolve().with_name("legacy_to_omg_migrate.py")
    runpy.run_path(str(target), run_name="__main__")

