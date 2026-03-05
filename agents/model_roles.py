#!/usr/bin/env python3
"""Model roles loader — defines role configurations for model selection.

Loads role definitions from _model_roles.yaml and provides utilities for
role-based model selection, CLI argument parsing, and feature flag control.
"""
import os
import sys
import json
from pathlib import Path
from typing import Any, Optional

# Try to import yaml; fall back to json if not available
try:
    import yaml
except ImportError:
    yaml = None

HAS_YAML = yaml is not None

# Add parent directory to path for importing from hooks
_AGENTS_DIR = Path(__file__).parent
_HOOKS_DIR = _AGENTS_DIR.parent / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

try:
    from _common import get_feature_flag, get_project_dir  # pyright: ignore[reportMissingImports]
except ImportError:
    # Fallback if _common is not available
    def get_feature_flag(flag_name, default=True):
        env_key = f"OMG_{flag_name.upper()}_ENABLED"
        env_val = os.environ.get(env_key, "").lower()
        if env_val in ("0", "false", "no"):
            return False
        if env_val in ("1", "true", "yes"):
            return True
        return default

    def get_project_dir():
        return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


# Global roles dictionary
RoleConfig = dict[str, Any]
RoleMap = dict[str, RoleConfig]

_roles: RoleMap = {}


def _load_roles() -> RoleMap:
    """Load role definitions from _model_roles.yaml.
    
    Returns:
        Dictionary mapping role names to role configurations.
        Falls back to default roles if YAML cannot be loaded.
    """
    roles_file = _AGENTS_DIR / "_model_roles.yaml"
    
    if not roles_file.exists():
        return _get_default_roles()
    
    try:
        if HAS_YAML and yaml is not None:
            with open(roles_file, "r") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict) and "roles" in data:
                    roles = {
                        role_name: dict(role_config)
                        for role_name, role_config in data["roles"].items()
                    }

                    plan_type = _get_plan_type()
                    if plan_type == "pro":
                        overrides = data.get("plan_type_overrides", {}).get("pro", {})
                        for role_name, override in overrides.items():
                            if role_name in roles:
                                roles[role_name].update(override)
                            else:
                                roles[role_name] = dict(override)

                    return roles
    except Exception as e:
        print(f"[OMG] Warning: Failed to load roles from {roles_file}: {e}", file=sys.stderr)

    
    return _get_default_roles()


def _get_plan_type() -> str:
    """Return configured _omg.plan_type from settings.json, defaulting to max."""
    settings_file = Path(get_project_dir()) / "settings.json"

    try:
        with open(settings_file, "r") as f:
            settings_data = json.load(f)
    except Exception:
        return "max"

    plan_type = settings_data.get("_omg", {}).get("plan_type", "max")
    if not isinstance(plan_type, str):
        return "max"

    normalized = plan_type.strip().lower()
    return normalized or "max"


def _get_default_roles() -> RoleMap:
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


def get_role(name: str) -> RoleConfig:
    """Get role configuration by name.
    
    Args:
        name: Role name (e.g., 'smol', 'slow', 'plan', 'commit', 'default')
    
    Returns:
        Role configuration dictionary. Returns 'default' role if name not found.
    """
    if not _roles:
        _init_roles()
    
    return _roles.get(name, _roles.get("default", {}))


def list_roles() -> list[str]:
    """Get list of all available role names.
    
    Returns:
        List of role names in order they appear in configuration.
    """
    if not _roles:
        _init_roles()
    
    return list(_roles.keys())


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
    global _roles
    _roles = _load_roles()


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
        print(json_module.dumps(_roles, indent=2))
