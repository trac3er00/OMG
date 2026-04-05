#!/usr/bin/env python3
import os
import json
import sys
import shutil
import time


def detect_provider():
    if os.getenv("CLAUDE_CODE"):
        return "claude"
    elif os.getenv("CODEX"):
        return "codex"
    elif os.getenv("OPENCODE"):
        return "opencode"
    elif os.getenv("GEMINI"):
        return "gemini"

    for cli in ["claude", "codex", "opencode", "gemini"]:
        if shutil.which(cli):
            return cli

    return "unknown"


def main():
    provider = detect_provider()
    adapter_path = f"hooks/universal/adapters/{provider}.py"
    if os.path.exists(adapter_path):
        print(f"Loading {provider} adapter...")

    output = {
        "provider": provider,
        "session_id": os.getenv("OMG_SESSION_ID", "unknown"),
        "timestamp": {"$date": {"$numberLong": str(int(time.time() * 1000))}},
        "universal_hooks_active": True,
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
