#!/usr/bin/env python3
"""Model roles loader — defines role configurations for model selection.

Loads role definitions from _model_roles.yaml and provides utilities for
role-based model selection, CLI argument parsing, and feature flag control.
"""
import os
import sys
from pathlib import Path
from typing import Optional

# Try to import yaml; fall back to json if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    import json

# Add parent directory to path for importing from hooks
_AGENTS_DIR = Path(__file__).parent
_HOOKS_DIR = _AGENTS_DIR.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

try:
    from _common import get_feature_flag, get_project_dir
except ImportError:
    # Fallback if _common is not available
    def get_feature_flag(flag_name, default=True):
        env_key = f"OAL_{flag_name.upper()}_ENABLED"
        env_val = os.environ.get(env_key, "").lower()
        if env_val in ("0", "false", "no"):
            return False
        if env_val in ("1", "true", "yes"):
            return True
        return default

    def get_project_dir():
        return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


# Global roles dictionary
ROLES: dict = {}


def _load_roles() -> dict:
    """Load role definitions from _model_roles.yaml.
    
    Returns:
        Dictionary mapping role names to role configurations.
        Falls back to default roles if YAML cannot be loaded.
    """
    roles_file = _AGENTS_DIR / "_model_roles.yaml"
    
    if not roles_file.exists():
        return _get_default_roles()
    
    try:
        if HAS_YAML:
            with open(roles_file, "r") as f:
                data = yaml.safe_load(f)
                if data and "roles" in data:
                    return data["roles"]
        else:
            # Fallback: try to parse as JSON
            with open(roles_file, "r") as f:
                data = json.load(f)
                if data and "roles" in data:
                    return data["roles"]
    except Exception as e:
        print(f"[OAL] Warning: Failed to load roles from {roles_file}: {e}", file=sys.stderr)
    
    return _get_default_roles()


def _get_default_roles() -> dict:
    """Return hardcoded default roles if YAML cannot be loaded."""
    return {
        "default": {
            "model": "claude-opus-4-5",
            "temperature": 1.0,
            "max_tokens": 8192,
            "description": "Default balanced model for general tasks"
        },
        "smol": {
            "model": "claude-haiku-4-5",
            "temperature": 0.7,
            "max_tokens": 4096,
            "description": "Fast cheap model for simple/trivial tasks"
        },
        "slow": {
            "model": "claude-opus-4-5",
            "temperature": 0.5,
            "max_tokens": 16384,
            "description": "Careful deliberate model for complex reasoning"
        },
        "plan": {
            "model": "claude-sonnet-4-5",
            "temperature": 0.8,
            "max_tokens": 8192,
            "description": "Planning and architecture model"
        },
        "commit": {
            "model": "claude-haiku-4-5",
            "temperature": 0.3,
            "max_tokens": 2048,
            "description": "Concise model for git commits and short summaries"
        }
    }


def get_role(name: str) -> dict:
    """Get role configuration by name.
    
    Args:
        name: Role name (e.g., 'smol', 'slow', 'plan', 'commit', 'default')
    
    Returns:
        Role configuration dictionary. Returns 'default' role if name not found.
    """
    if not ROLES:
        _init_roles()
    
    return ROLES.get(name, ROLES.get("default", {}))


def list_roles() -> list[str]:
    """Get list of all available role names.
    
    Returns:
        List of role names in order they appear in configuration.
    """
    if not ROLES:
        _init_roles()
    
    return list(ROLES.keys())


def parse_role_args(argv: list[str]) -> Optional[str]:
    """Parse command-line arguments to detect role selection.
    
    Detects: --smol, --slow, --plan, --commit
    
    Args:
        argv: Command-line arguments (typically sys.argv[1:])
    
    Returns:
        Role name if detected, None otherwise.
    """
    role_map = {
        "--smol": "smol",
        "--slow": "slow",
        "--plan": "plan",
        "--commit": "commit",
    }
    
    for arg in argv:
        if arg in role_map:
            return role_map[arg]
    
    return None


def _init_roles() -> None:
    """Initialize the global ROLES dictionary."""
    global ROLES
    ROLES = _load_roles()


# Initialize on module import
_init_roles()


if __name__ == "__main__":
    # CLI for testing/inspection
    import json as json_module
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            print("Available roles:")
            for role_name in list_roles():
                print(f"  - {role_name}")
        elif sys.argv[1] == "get":
            if len(sys.argv) > 2:
                role_name = sys.argv[2]
                role = get_role(role_name)
                print(json_module.dumps(role, indent=2))
            else:
                print("Usage: python3 model_roles.py get <role_name>")
        elif sys.argv[1] == "parse":
            detected = parse_role_args(sys.argv[2:])
            if detected:
                print(f"Detected role: {detected}")
            else:
                print("No role detected")
        else:
            print("Usage: python3 model_roles.py [list|get <role>|parse <args...>]")
    else:
        # Default: print all roles
        print(json_module.dumps(ROLES, indent=2))
