from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import NotRequired, TypedDict, cast

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


class ManifestPack(TypedDict, total=False):
    description: str
    entry_modules: list[str]
    dependencies: NotRequired[list[str]]
    trigger: NotRequired[str]


class PackListing(TypedDict):
    name: str
    description: str
    entry_modules: list[str]
    loaded: bool
    load_time_ms: float


_DEFAULT_MANIFEST = Path(__file__).parent.parent / "config" / "packs.yaml"


def _load_manifest(path: Path | None = None) -> dict[str, ManifestPack]:
    manifest_path = path or _DEFAULT_MANIFEST
    if _yaml is None:
        return {}
    try:
        loaded = cast(
            object, _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        )
    except Exception:
        return {}

    if not isinstance(loaded, dict):
        return {}

    raw_root = cast(dict[object, object], loaded)
    raw_packs = raw_root.get("packs")
    if not isinstance(raw_packs, dict):
        return {}

    manifest: dict[str, ManifestPack] = {}
    for pack_name, pack_info in cast(dict[object, object], raw_packs).items():
        if not isinstance(pack_name, str) or not isinstance(pack_info, dict):
            continue
        raw_pack_info = cast(dict[object, object], pack_info)
        entry_modules = raw_pack_info.get("entry_modules")
        description = raw_pack_info.get("description")
        if not isinstance(description, str) or not _is_string_list(entry_modules):
            continue
        entry_module_list = cast(list[str], entry_modules)
        pack_entry: ManifestPack = {
            "description": description,
            "entry_modules": entry_module_list,
        }
        dependencies = raw_pack_info.get("dependencies")
        if _is_string_list(dependencies):
            pack_entry["dependencies"] = cast(list[str], dependencies)
        trigger = raw_pack_info.get("trigger")
        if isinstance(trigger, str):
            pack_entry["trigger"] = trigger
        manifest[pack_name] = pack_entry
    return manifest


def _is_string_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    items = cast(list[object], value)
    return all(isinstance(item, str) for item in items)


class PackLoader:
    def __init__(self, manifest_path: Path | None = None):
        self._manifest: dict[str, ManifestPack] = _load_manifest(manifest_path)
        self._loaded: dict[str, float] = {}
        self._modules: dict[str, ModuleType] = {}

    def is_pack_module(self, module_name: str) -> bool:
        for pack_info in self._manifest.values():
            entry_modules = pack_info.get("entry_modules", [])
            if module_name in entry_modules:
                return True
        return False

    def load_pack(self, pack_name: str) -> bool:
        if pack_name in self._loaded:
            return True

        pack_info = self._manifest.get(pack_name)
        if not pack_info:
            return False

        start = time.perf_counter()
        success = True

        for module_name in pack_info.get("entry_modules", []):
            try:
                if module_name not in sys.modules:
                    mod = importlib.import_module(module_name)
                    self._modules[module_name] = mod
            except ImportError:
                success = False

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._loaded[pack_name] = elapsed_ms
        return success

    def get_load_stats(self) -> dict[str, float]:
        return dict(self._loaded)

    def is_core_import_clean(self) -> bool:
        pack_modules: set[str] = set()
        for pack_info in self._manifest.values():
            pack_modules.update(pack_info.get("entry_modules", []))

        loaded_pack_modules = [
            module for module in sys.modules if module in pack_modules
        ]
        return len(loaded_pack_modules) == 0

    def list_packs(self) -> list[dict[str, object]]:
        packs: list[PackListing] = []
        for name, info in self._manifest.items():
            packs.append(
                {
                    "name": name,
                    "description": info.get("description", ""),
                    "entry_modules": info.get("entry_modules", []),
                    "loaded": name in self._loaded,
                    "load_time_ms": self._loaded.get(name, 0.0),
                }
            )
        return packs


_default_loader: PackLoader | None = None


def get_loader() -> PackLoader:
    global _default_loader
    if _default_loader is None:
        _default_loader = PackLoader()
    return _default_loader
