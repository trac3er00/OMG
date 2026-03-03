#!/usr/bin/env python3
"""
Config Discovery Framework for AI Coding Tools

Scans a project directory for configuration files from 8 AI coding tools
and produces a JSON discovery report. Read-only operation.

Feature flag: OAL_CONFIG_DISCOVERY_ENABLED (default: off)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Feature flag
OAL_CONFIG_DISCOVERY_ENABLED = os.getenv("OAL_CONFIG_DISCOVERY_ENABLED", "false").lower() == "true"

# Tool detection patterns
TOOL_PATTERNS = {
    "claude_code": [".claude/", ".claude/CLAUDE.md", "CLAUDE.md"],
    "cursor": [".cursorrules", ".cursor/rules/", ".cursor/"],
    "windsurf": [".windsurf/", ".windsurfrules"],
    "gemini": ["system.md", ".gemini/"],
    "codex": ["AGENTS.md"],
    "cline": [".clinerules"],
    "github_copilot": [".github/copilot-instructions.md"],
    "vscode": [".vscode/settings.json", ".vscode/"],
}


def get_file_size(path: Path) -> int:
    """Get file size in bytes. Returns 0 if not a file."""
    try:
        if path.is_file():
            return path.stat().st_size
        return 0
    except (OSError, ValueError):
        return 0


def is_readable(path: Path) -> bool:
    """Check if path is readable."""
    try:
        return os.access(str(path), os.R_OK)
    except (OSError, ValueError):
        return False


def get_format(path: Path) -> str:
    """Determine file format from extension or path."""
    if path.is_dir():
        return "directory"
    
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    elif suffix == ".json":
        return "json"
    elif suffix == ".yaml" or suffix == ".yml":
        return "yaml"
    elif suffix == ".txt":
        return "text"
    else:
        return "unknown"


def discover_configs(project_dir: str) -> Dict[str, Any]:
    """
    Scan project_dir for AI tool configs.
    
    Returns:
        {
            "discovered": [
                {
                    "tool": "claude_code",
                    "paths": [".claude/CLAUDE.md"],
                    "format": "markdown",
                    "size_bytes": 1234,
                    "readable": true
                },
                ...
            ],
            "scan_dir": "/path/to/project",
            "timestamp": "2025-03-02T10:30:45.123456"
        }
    """
    project_path = Path(project_dir).resolve()
    
    if not project_path.exists():
        return {
            "discovered": [],
            "scan_dir": str(project_path),
            "timestamp": datetime.now().isoformat(),
            "error": f"Project directory does not exist: {project_dir}"
        }
    
    discovered = []
    
    for tool_name, patterns in TOOL_PATTERNS.items():
        tool_paths = []
        
        for pattern in patterns:
            # Handle directory patterns (ending with /)
            if pattern.endswith("/"):
                dir_path = project_path / pattern.rstrip("/")
                if dir_path.exists() and dir_path.is_dir():
                    tool_paths.append(pattern.rstrip("/"))
            else:
                # Handle file patterns
                file_path = project_path / pattern
                if file_path.exists():
                    tool_paths.append(pattern)
        
        if tool_paths:
            # Get info from first discovered path
            first_path = project_path / tool_paths[0]
            size_bytes = get_file_size(first_path)
            readable = is_readable(first_path)
            format_type = get_format(first_path)
            
            discovered.append({
                "tool": tool_name,
                "paths": tool_paths,
                "format": format_type,
                "size_bytes": size_bytes,
                "readable": readable
            })
    
    return {
        "discovered": discovered,
        "scan_dir": str(project_path),
        "timestamp": datetime.now().isoformat()
    }


def main():
    """CLI entry point."""
    if len(sys.argv) < 3 or sys.argv[1] != "--scan":
        print("Usage: python3 config_discovery.py --scan <directory>", file=sys.stderr)
        sys.exit(1)
    
    project_dir = sys.argv[2]
    result = discover_configs(project_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
