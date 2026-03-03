#!/usr/bin/env python3
"""Legacy wrapper for OMG compatibility snapshot checker."""
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    target = Path(__file__).resolve().with_name("check-omg-compat-contract-snapshot.py")
    runpy.run_path(str(target), run_name="__main__")

