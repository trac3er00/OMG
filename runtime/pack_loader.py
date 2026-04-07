from __future__ import annotations

import importlib
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Callable, NotRequired, TypedDict, cast

import runtime.core_imports as _core_imports  # pyright: ignore[reportMissingImports]

CORE_MODULES: list[str] = cast(list[str], getattr(_core_imports, "CORE_MODULES"))
eager_import_core_modules = cast(
    Callable[[], dict[str, ModuleType]],
    getattr(_core_imports, "eager_import_core_modules"),
)

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
_RUNTIME_DIR = Path(__file__).parent

_DISCOVERED_PACK_SPECS: dict[str, ManifestPack] = {
    "vision": {
        "description": "Vision/OCR capabilities for image processing",
        "entry_modules": [
            "runtime.vision_artifacts",
            "runtime.vision_jobs",
        ],
        "dependencies": [],
        "trigger": "from runtime.vision_",
    },
    "browser": {
        "description": "Browser automation via Playwright",
        "entry_modules": [
            "runtime.playwright_adapter",
            "runtime.playwright_pack",
        ],
        "dependencies": [],
        "trigger": "from runtime.playwright_",
    },
    "music-omr": {
        "description": "Music OCR and transposition engine",
        "entry_modules": ["runtime.music_omr_testbed"],
        "dependencies": [],
        "trigger": "from runtime.music_omr",
    },
    "api-twin": {
        "description": "API cassette replay and twin testing",
        "entry_modules": ["runtime.api_twin"],
        "dependencies": [],
        "trigger": "from runtime.api_twin",
    },
    "data-lineage": {
        "description": "Data provenance and lineage tracking",
        "entry_modules": ["runtime.data_lineage"],
        "dependencies": [],
        "trigger": "from runtime.data_lineage",
    },
    "eval": {
        "description": "Evaluation and regression gates",
        "entry_modules": ["runtime.eval_gate"],
        "dependencies": [],
        "trigger": "from runtime.eval_",
    },
}


def _module_exists(module_name: str) -> bool:
    if not module_name.startswith("runtime."):
        return importlib.util.find_spec(module_name) is not None

    module_path = module_name.removeprefix("runtime.").replace(".", "/")
    file_candidate = _RUNTIME_DIR / f"{module_path}.py"
    package_candidate = _RUNTIME_DIR / module_path / "__init__.py"
    return file_candidate.exists() or package_candidate.exists()


def _merge_manifest_with_defaults(
    manifest: dict[str, ManifestPack],
) -> dict[str, ManifestPack]:
    merged: dict[str, ManifestPack] = {}
    for pack_name, discovered in _DISCOVERED_PACK_SPECS.items():
        configured = manifest.get(pack_name, {})
        configured_entry_modules = [
            module_name
            for module_name in configured.get("entry_modules", [])
            if _module_exists(module_name)
        ]
        discovered_entry_modules = [
            module_name
            for module_name in discovered.get("entry_modules", [])
            if _module_exists(module_name)
        ]
        entry_modules = list(
            dict.fromkeys(configured_entry_modules + discovered_entry_modules)
        )
        if not entry_modules:
            continue
        merged[pack_name] = {
            "description": configured.get("description")
            or discovered.get("description")
            or pack_name,
            "entry_modules": entry_modules,
        }
        dependencies = configured.get("dependencies") or discovered.get("dependencies")
        if _is_string_list(dependencies):
            merged[pack_name]["dependencies"] = cast(list[str], dependencies)
        trigger = configured.get("trigger") or discovered.get("trigger")
        if isinstance(trigger, str):
            merged[pack_name]["trigger"] = trigger

    for pack_name, pack_info in manifest.items():
        if pack_name in merged:
            continue
        entry_modules = [
            module_name
            for module_name in pack_info.get("entry_modules", [])
            if _module_exists(module_name)
        ]
        if not entry_modules:
            continue
        merged[pack_name] = {
            "description": pack_info.get("description", pack_name),
            "entry_modules": entry_modules,
        }
        dependencies = pack_info.get("dependencies")
        if _is_string_list(dependencies):
            merged[pack_name]["dependencies"] = cast(list[str], dependencies)
        trigger = pack_info.get("trigger")
        if isinstance(trigger, str):
            merged[pack_name]["trigger"] = trigger

    return merged


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
        start = time.perf_counter()
        self._core_modules: dict[str, ModuleType] = {}
        self._manifest: dict[str, ManifestPack] = {}
        self._startup_stats: dict[str, float | int] = {}
        self._core_modules = eager_import_core_modules()
        self._manifest = _merge_manifest_with_defaults(_load_manifest(manifest_path))
        self._loaded: dict[str, float] = {}
        self._modules: dict[str, ModuleType] = {}
        self._startup_stats = {
            "startup_time_ms": (time.perf_counter() - start) * 1000,
            "core_module_count": len(CORE_MODULES),
            "pack_count": len(self._manifest),
        }

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

    def get_startup_stats(self) -> dict[str, float | int]:
        return dict(self._startup_stats)

    def is_core_import_clean(self) -> bool:
        pack_modules: set[str] = set()
        for pack_info in self._manifest.values():
            pack_modules.update(pack_info.get("entry_modules", []))

        loaded_pack_modules = [
            module for module in sys.modules if module in pack_modules
        ]
        return len(loaded_pack_modules) == 0

    def list_packs(self) -> list[PackListing]:
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
