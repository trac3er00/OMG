#!/usr/bin/env python3
"""Compatibility entrypoint for the canonical UserPromptSubmit hook."""
from __future__ import annotations

import runpy
from pathlib import Path


HOOK_PATH = Path(__file__).with_name("prompt-enhancer.py")

if __name__ == "__main__":
    runpy.run_path(str(HOOK_PATH), run_name="__main__")
