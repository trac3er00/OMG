"""LSP Server Auto-Discovery Tool

Scans for available LSP servers based on language configurations.
Searches in: node_modules/.bin/, .venv/bin/, system PATH

Feature flag: OMG_LSP_TOOLS_ENABLED (default: False)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to load YAML, fall back to JSON
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _load_language_config(project_dir: str = ".") -> dict[str, Any]:
    """Load language configuration from YAML or JSON.
    
    Returns dict with 'languages' key containing list of language configs.
    Falls back to empty dict if file not found.
    """
    config_path = Path(project_dir) / "config" / "lsp_languages.yaml"
    
    if not config_path.exists():
        return {"languages": []}
    
    try:
        if HAS_YAML:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {"languages": []}
        else:
            # Fallback: try to parse as JSON
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Simple YAML to JSON conversion for basic cases
                # This is a minimal fallback - just try JSON first
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # If JSON fails, return empty config
                    return {"languages": []}
    except Exception as e:
        logger.error(f"Failed to load language config: {e}")
        return {"languages": []}


def _expand_path(path_str: str) -> str:
    """Expand ~ and environment variables in path."""
    return os.path.expanduser(os.path.expandvars(path_str))


def _find_in_paths(binary_name: str, search_paths: list[str]) -> str | None:
    """Find binary in list of paths.
    
    Args:
        binary_name: Name of binary to find (e.g., 'pylsp')
        search_paths: List of paths to search (may contain ~ and env vars)
    
    Returns:
        Full path to binary if found, None otherwise
    """
    for path_str in search_paths:
        expanded = _expand_path(path_str)
        
        # If path is a directory, look for binary inside
        if os.path.isdir(expanded):
            binary_path = os.path.join(expanded, binary_name)
            if os.path.isfile(binary_path) and os.access(binary_path, os.X_OK):
                return binary_path
        # If path is a file, check if it matches
        elif os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            if os.path.basename(expanded) == binary_name:
                return expanded
    
    return None


def _find_in_system_path(binary_name: str) -> str | None:
    """Find binary in system PATH.
    
    Args:
        binary_name: Name of binary to find
    
    Returns:
        Full path to binary if found, None otherwise
    """
    return shutil.which(binary_name)


def discover_lsp_servers(project_dir: str = ".") -> list[dict[str, Any]]:
    """Discover available LSP servers in project.
    
    Scans for LSP servers defined in config/lsp_languages.yaml.
    For each language, checks discovery_paths and system PATH.
    
    Args:
        project_dir: Project directory to scan (default: current directory)
    
    Returns:
        List of dicts with keys:
        - language: Language name
        - server_command: Command to start server
        - server_name: Human-readable server name
        - found_at: Full path to server binary (or None if not found)
        - available: Boolean indicating if server was found
    """
    config = _load_language_config(project_dir)
    languages = config.get("languages", [])
    
    discovered = []
    
    for lang_config in languages:
        language = lang_config.get("name", "unknown")
        server_command = lang_config.get("server_command", [])
        server_name = lang_config.get("server_name", "unknown")
        discovery_paths = lang_config.get("discovery_paths", [])
        
        # Get the binary name (first element of server_command)
        if not server_command:
            discovered.append({
                "language": language,
                "server_command": server_command,
                "server_name": server_name,
                "found_at": None,
                "available": False,
            })
            continue
        
        binary_name = server_command[0]
        
        # Search in discovery_paths first
        found_at = _find_in_paths(binary_name, discovery_paths)
        
        # Fall back to system PATH
        if not found_at:
            found_at = _find_in_system_path(binary_name)
        
        discovered.append({
            "language": language,
            "server_command": server_command,
            "server_name": server_name,
            "found_at": found_at,
            "available": found_at is not None,
        })
    
    return discovered


def _is_enabled() -> bool:
    """Check if LSP discovery is enabled via feature flag.
    
    Checks env var first (OMG_LSP_TOOLS_ENABLED), then settings.json.
    """
    # Check environment variable
    env_val = os.environ.get("OMG_LSP_TOOLS_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    
    # Check settings.json
    try:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        settings_path = os.path.join(project_dir, "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                features = settings.get("_omg", {}).get("features", {})
                if "LSP_TOOLS" in features:
                    return features["LSP_TOOLS"]
    except Exception:
        pass
    
    # Default: disabled (opt-in)
    return False


def main():
    """CLI entry point for LSP discovery.
    
    Usage:
        python3 tools/lsp_discovery.py --project <dir>
    
    Outputs JSON to stdout with list of discovered servers.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Discover available LSP servers in project"
    )
    parser.add_argument(
        "--project",
        default=".",
        help="Project directory to scan (default: current directory)"
    )
    
    args = parser.parse_args()
    
    # Discover servers (works regardless of feature flag)
    servers = discover_lsp_servers(args.project)
    
    # Output as JSON
    output = {
        "project_dir": os.path.abspath(args.project),
        "enabled": _is_enabled(),
        "servers": servers,
        "summary": {
            "total": len(servers),
            "available": sum(1 for s in servers if s["available"]),
            "unavailable": sum(1 for s in servers if not s["available"]),
        }
    }
    
    json.dump(output, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
