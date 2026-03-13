#!/usr/bin/env python3
"""Claude InstructionsLoaded compatibility hook.

This event currently has no OMG-side behavior, but the hook must exist so
post-install command surfaces do not fail when Claude emits the event.
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            json.loads(raw)
    except Exception:
        return 0

    json.dump({}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
