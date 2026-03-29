#!/usr/bin/env python3
import os
import shutil

PROVIDER_ADAPTERS = {
    "claude": "adapters/claude_adapter.py",
    "codex": "adapters/codex_adapter.py",
    "opencode": "adapters/opencode_adapter.py",
    "gemini": "adapters/gemini_adapter.py",
}

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

def get_adapter_path(provider=None):
    provider = provider or detect_provider()
    return PROVIDER_ADAPTERS.get(provider)

def load_adapter(provider=None):
    provider = provider or detect_provider()
    adapter_file = get_adapter_path(provider)
    if adapter_file and os.path.exists(adapter_file):
        return adapter_file
    return None
