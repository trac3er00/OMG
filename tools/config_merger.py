#!/usr/bin/env python3
"""
Config Merging Framework for OMG

Merges discovered AI tool configurations into a unified OMG config with
priority-based conflict resolution.

Priority order (highest to lowest):
  1. OMG config (.omg/state/omg_config.json)
  2. Project-level configs (discovered in project directory)
  3. User-level configs (discovered in home directory)
  4. Tool defaults

Feature flag: OMG_CONFIG_DISCOVERY_ENABLED (default: off)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


# Priority levels — lower number = higher priority
PRIORITY_OMG = 0
PRIORITY_PROJECT = 10
PRIORITY_USER = 20
PRIORITY_DEFAULT = 30

# Source type labels
SOURCE_OMG = "omg_config"
SOURCE_PROJECT = "project"
SOURCE_USER = "user"
SOURCE_DEFAULT = "default"

_logger = logging.getLogger(__name__)


def _get_feature_flag_enabled() -> bool:
    """Check if config discovery feature is enabled.

    Resolution: env var → _common.get_feature_flag() → False.
    """
    env_val = os.environ.get("OMG_CONFIG_DISCOVERY_ENABLED", "").lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True

    # Lazy import from hooks
    hooks_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
    )
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import get_feature_flag  # type: ignore[import-untyped]

        return get_feature_flag("CONFIG_DISCOVERY", default=False)
    except ImportError:
        return False


def _get_atomic_json_write():
    """Lazy-import atomic_json_write from hooks/_common.py."""
    hooks_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
    )
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        from _common import atomic_json_write  # type: ignore[import-untyped]

        return atomic_json_write
    except ImportError:
        return None


def _extract_config_values(config_path: str, fmt: str) -> Dict[str, Any]:
    """Extract key-value pairs from a config file.

    Handles JSON, YAML (if available), TOML (if available), and
    markdown (extracts frontmatter).

    Returns empty dict on any parse error — never crashes.
    """
    if not config_path or not os.path.isfile(config_path):
        return {}

    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(256 * 1024)  # 256KB limit
    except (OSError, IOError):
        return {}

    if not content.strip():
        return {}

    # JSON
    if fmt == "json":
        return _parse_json(content)

    # YAML
    if fmt in ("yaml", "yml"):
        return _parse_yaml(content)

    # TOML
    if fmt == "toml":
        return _parse_toml(content)

    # Markdown — extract frontmatter
    if fmt == "markdown":
        return _parse_markdown_frontmatter(content)

    # Unknown format — try JSON first, then YAML
    result = _parse_json(content)
    if result:
        return result
    return _parse_yaml(content)


def _parse_json(content: str) -> Dict[str, Any]:
    """Parse JSON content into a dict."""
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _parse_yaml(content: str) -> Dict[str, Any]:
    """Parse YAML content. Returns empty dict if PyYAML not available."""
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(content)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return {}
    except Exception:
        _logger.debug("Failed to parse YAML config", exc_info=True)
        return {}


def _parse_toml(content: str) -> Dict[str, Any]:
    """Parse TOML content. Tries tomllib (3.11+), then tomli, then fails gracefully."""
    try:
        import tomllib  # type: ignore[import-not-found]  # Python 3.11+

        data = tomllib.loads(content)
        return data if isinstance(data, dict) else {}
    except ImportError:
        # Optional: tomllib not available
        _logger.debug("Failed to import tomllib parser", exc_info=True)
    except Exception:
        _logger.debug("Failed to parse TOML with tomllib", exc_info=True)
        return {}

    try:
        import tomli  # type: ignore[import-untyped]

        data = tomli.loads(content)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return {}
    except Exception:
        _logger.debug("Failed to parse TOML with tomli", exc_info=True)
        return {}


def _parse_markdown_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML frontmatter from markdown (between --- delimiters)."""
    content = content.strip()
    if not content.startswith("---"):
        return {}

    # Find the closing ---
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return {}

    frontmatter = content[3:end_idx].strip()
    if not frontmatter:
        return {}

    return _parse_yaml(frontmatter)


def _classify_source(config: Dict[str, Any]) -> str:
    """Classify a discovered config as project-level or user-level.

    Heuristic: configs from home directory paths are user-level,
    everything else is project-level.
    """
    paths = config.get("paths", [])
    if not paths:
        return SOURCE_PROJECT

    first_path = str(paths[0])
    home = os.path.expanduser("~")

    # If the path is absolute and under home dir (not in project), it's user-level
    if os.path.isabs(first_path) and first_path.startswith(home):
        return SOURCE_USER

    return SOURCE_PROJECT


def _get_priority(source_type: str) -> int:
    """Get numeric priority for a source type. Lower = higher priority."""
    return {
        SOURCE_OMG: PRIORITY_OMG,
        SOURCE_PROJECT: PRIORITY_PROJECT,
        SOURCE_USER: PRIORITY_USER,
        SOURCE_DEFAULT: PRIORITY_DEFAULT,
    }.get(source_type, PRIORITY_DEFAULT)


def _resolve_conflict(
    key: str,
    existing_val: Any,
    new_val: Any,
    existing_source: str,
    new_source: str,
) -> Tuple[Any, Dict[str, Any]]:
    """Resolve a config key conflict between two sources.

    Priority rules: higher priority source (lower number) wins.
    If same priority, last-write-wins (new_val wins).

    Returns:
        (winning_value, conflict_record) where conflict_record is a dict
        documenting the conflict for logging.
    """
    existing_priority = _get_priority(existing_source)
    new_priority = _get_priority(new_source)

    conflict_record = {
        "key": key,
        "existing_value": existing_val,
        "existing_source": existing_source,
        "new_value": new_val,
        "new_source": new_source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if new_priority < existing_priority:
        # New source has higher priority (lower number) — it wins
        conflict_record["winner"] = new_source
        conflict_record["resolution"] = "higher_priority"
        return new_val, conflict_record
    elif new_priority > existing_priority:
        # Existing source has higher priority — it wins
        conflict_record["winner"] = existing_source
        conflict_record["resolution"] = "higher_priority"
        return existing_val, conflict_record
    else:
        # Same priority — last-write-wins
        conflict_record["winner"] = new_source
        conflict_record["resolution"] = "last_write_wins"
        return new_val, conflict_record


def _load_omg_config(omg_config_path: str) -> Dict[str, Any]:
    """Load OMG config from disk. Returns empty dict on any error."""
    if not omg_config_path or not os.path.isfile(omg_config_path):
        return {}
    try:
        with open(omg_config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, IOError):
        return {}


def merge_configs(
    discovered_configs: List[Dict[str, Any]],
    omg_config_path: str = ".omg/state/omg_config.json",
) -> Dict[str, Any]:
    """Merge discovered AI tool configs into a unified OMG config.

    Args:
        discovered_configs: List of config dicts from discover_configs()["discovered"].
            Each dict has: tool, paths, format, size_bytes, readable.
        omg_config_path: Path to existing OMG config (highest priority).

    Returns:
        {
            "merged": dict — the merged configuration,
            "conflicts": list — conflict records,
            "sources": list — source descriptions,
            "timestamp": str — ISO 8601 timestamp,
        }
        or {"skipped": True} if feature flag is disabled.
    """
    if not _get_feature_flag_enabled():
        return {"skipped": True}

    merged: Dict[str, Any] = {}
    conflicts: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    source_map: Dict[str, str] = {}  # key → source label for conflict tracking

    # Phase 1: Load OMG config (highest priority)
    omg_values = _load_omg_config(omg_config_path)
    if omg_values:
        sources.append({
            "type": SOURCE_OMG,
            "path": omg_config_path,
            "keys_count": len(omg_values),
        })
        for key, val in omg_values.items():
            merged[key] = val
            source_map[key] = SOURCE_OMG

    # Phase 2: Process discovered configs by priority
    # Sort: project-level first, then user-level
    sorted_configs = sorted(
        discovered_configs or [],
        key=lambda c: _get_priority(_classify_source(c)),
    )

    for config in sorted_configs:
        tool = config.get("tool", "unknown")
        paths = config.get("paths", [])
        fmt = config.get("format", "unknown")
        readable = config.get("readable", False)

        if not paths or not readable:
            continue

        first_path = paths[0]
        source_type = _classify_source(config)
        source_label = f"{source_type}:{tool}:{first_path}"

        # Extract values from the config file
        values = _extract_config_values(first_path, fmt)
        if not values:
            continue

        sources.append({
            "type": source_type,
            "tool": tool,
            "path": first_path,
            "format": fmt,
            "keys_count": len(values),
        })

        for key, val in values.items():
            if key in merged:
                # Conflict — resolve with priority rules
                winning_val, conflict_record = _resolve_conflict(
                    key,
                    merged[key],
                    val,
                    source_map.get(key, SOURCE_DEFAULT),
                    source_label,
                )
                conflicts.append(conflict_record)
                merged[key] = winning_val
                if conflict_record["winner"] == source_label:
                    source_map[key] = source_label
            else:
                merged[key] = val
                source_map[key] = source_label

    result = {
        "merged": merged,
        "conflicts": conflicts,
        "sources": sources,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Persist merged config
    _persist_merged_config(result)

    # Persist conflict log if any conflicts
    if conflicts:
        _persist_conflicts(conflicts)

    return result


def _persist_merged_config(result: Dict[str, Any]) -> None:
    """Persist merged config to .omg/state/merged_config.json."""
    writer = _get_atomic_json_write()
    if writer is None:
        return
    try:
        merged_path = os.path.join(".omg", "state", "merged_config.json")
        writer(merged_path, result)
    except Exception:
        _logger.debug("Failed to persist merged config", exc_info=True)


def _persist_conflicts(conflicts: List[Dict[str, Any]]) -> None:
    """Persist conflict log to .omg/state/config_conflicts.json."""
    writer = _get_atomic_json_write()
    if writer is None:
        return
    try:
        conflicts_path = os.path.join(".omg", "state", "config_conflicts.json")
        writer(conflicts_path, conflicts)
    except Exception:
        _logger.debug("Failed to persist config conflicts", exc_info=True)


def get_merged_config() -> Dict[str, Any]:
    """Load and return the persisted merged config.

    Returns the full merged config dict from .omg/state/merged_config.json,
    or an empty dict if the file doesn't exist or is unreadable.
    """
    merged_path = os.path.join(".omg", "state", "merged_config.json")
    if not os.path.isfile(merged_path):
        return {}
    try:
        with open(merged_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, IOError):
        return {}


def main():
    """CLI entry point."""
    if len(sys.argv) < 3 or sys.argv[1] != "--merge":
        print(
            "Usage: python3 config_merger.py --merge <directory>",
            file=sys.stderr,
        )
        sys.exit(1)

    project_dir = sys.argv[2]

    # Lazy import discover_configs
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        from config_discovery import discover_configs  # type: ignore[import-untyped]
    except ImportError:
        print("Error: config_discovery module not available", file=sys.stderr)
        sys.exit(1)

    discovery = discover_configs(project_dir)
    discovered = discovery.get("discovered", [])

    omg_config_path = os.path.join(project_dir, ".omg", "state", "omg_config.json")
    result = merge_configs(discovered, omg_config_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
