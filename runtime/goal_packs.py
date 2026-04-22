"""Goal Pack loader and scaffold executor for OMG.

Goal packs scaffold runnable starter projects from `packs/goals/{name}/`.
Each goal pack is expected to define a `pack.yaml` and may include a
`scaffold/` directory whose files are copied into a target directory.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore[assignment]

_DEFAULT_GOAL_PACKS_DIR = Path(__file__).parent.parent / "packs" / "goals"
_DEFAULT_MANIFEST_PATH = Path(__file__).parent.parent / "config" / "packs.yaml"
_DEFAULT_SCHEMA_PATH = _DEFAULT_GOAL_PACKS_DIR / "schema.yaml"
_TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _resolve_pack_dir(pack_name: str, registry_entry: dict[str, Any] | None = None) -> Path:
    configured_path = (registry_entry or {}).get("path")
    if isinstance(configured_path, str) and configured_path.strip():
        return Path(__file__).parent.parent / configured_path
    return _DEFAULT_GOAL_PACKS_DIR / pack_name


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists() or _yaml is None:
        return {}
    try:
        loaded = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValueError(f"Failed to load YAML from {path}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return {str(key): value for key, value in loaded.items()}


def _load_goal_pack_registry() -> dict[str, dict[str, Any]]:
    manifest = _read_yaml_mapping(_DEFAULT_MANIFEST_PATH)
    raw_goal_packs = manifest.get("goal_packs")
    if not isinstance(raw_goal_packs, dict):
        return {}

    registry: dict[str, dict[str, Any]] = {}
    for pack_name, pack_info in raw_goal_packs.items():
        if not isinstance(pack_name, str) or not isinstance(pack_info, dict):
            continue
        registry[pack_name] = {str(key): value for key, value in pack_info.items()}
    return registry


def _load_schema() -> dict[str, list[str]]:
    schema = _read_yaml_mapping(_DEFAULT_SCHEMA_PATH)
    required_fields = schema.get("required_fields", [])
    optional_fields = schema.get("optional_fields", [])
    return {
        "required_fields": [
            str(field) for field in required_fields if isinstance(field, str) and field.strip()
        ],
        "optional_fields": [
            str(field) for field in optional_fields if isinstance(field, str) and field.strip()
        ],
    }


def _validate_goal_pack(pack_name: str, pack_data: dict[str, Any]) -> None:
    schema = _load_schema()
    required_fields = schema.get("required_fields", [])
    missing_fields = [field for field in required_fields if field not in pack_data]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"Goal pack '{pack_name}' is missing required fields: {missing}")


def _render_template(content: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            return match.group(0)
        return str(context[key])

    return _TEMPLATE_PATTERN.sub(replace, content)


def load_goal_pack(pack_name: str) -> dict[str, Any]:
    registry_entry = _load_goal_pack_registry().get(pack_name, {})
    pack_dir = _resolve_pack_dir(pack_name, registry_entry)
    pack_yaml = pack_dir / "pack.yaml"
    if not pack_yaml.exists():
        raise FileNotFoundError(f"Goal pack '{pack_name}' not found at {pack_yaml}")

    pack_data = _read_yaml_mapping(pack_yaml)
    merged_pack = dict(registry_entry)
    merged_pack.update(pack_data)
    merged_pack.setdefault("name", pack_name)
    merged_pack["pack"] = pack_name
    merged_pack["path"] = str(pack_dir)
    _validate_goal_pack(pack_name, merged_pack)
    return merged_pack


def list_goal_packs() -> list[str]:
    registered_names = set(_load_goal_pack_registry())
    discovered_names: set[str] = set()
    if _DEFAULT_GOAL_PACKS_DIR.exists():
        discovered_names = {
            pack_dir.name
            for pack_dir in _DEFAULT_GOAL_PACKS_DIR.iterdir()
            if pack_dir.is_dir() and (pack_dir / "pack.yaml").exists()
        }
    return sorted(registered_names | discovered_names)


def execute_goal_pack(pack_name: str, target_dir: str, context: dict[str, Any]) -> dict[str, Any]:
    pack = load_goal_pack(pack_name)
    scaffold_dir = Path(pack["path"]) / "scaffold"
    if not scaffold_dir.exists():
        return {
            "success": False,
            "error": f"Goal pack '{pack_name}' has no scaffold directory",
            "files": [],
        }

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    generated_files: list[str] = []
    rendered_files: list[str] = []

    for source in scaffold_dir.rglob("*"):
        if not source.is_file():
            continue
        relative_path = source.relative_to(scaffold_dir)
        destination = target / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            rendered_content = _render_template(
                source.read_text(encoding="utf-8"),
                context,
            )
        except UnicodeDecodeError:
            shutil.copy2(source, destination)
        else:
            destination.write_text(rendered_content, encoding="utf-8")
            rendered_files.append(str(relative_path))

        generated_files.append(str(relative_path))

    return {
        "success": True,
        "pack": pack_name,
        "target": str(target),
        "files": generated_files,
        "rendered_files": rendered_files,
        "context_keys": sorted(str(key) for key in context),
    }
