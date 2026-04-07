#!/usr/bin/env python3
import sys as _sys
import os as _os
import importlib.util as _util

_spec = _util.spec_from_file_location(
    "language_preserve",
    _os.path.join(_os.path.dirname(__file__), "language-preserve.py"),
)
_mod = _util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
main = _mod.main

if __name__ == "__main__":
    main()
