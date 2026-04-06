from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol, TypedDict, cast

ROOT = Path(__file__).resolve().parents[2]
PACK_LOADER_PATH = ROOT / "runtime" / "pack_loader.py"
PACK_LOADER_SPEC = importlib.util.spec_from_file_location(
    "test_pack_loader_module", PACK_LOADER_PATH
)
assert PACK_LOADER_SPEC is not None and PACK_LOADER_SPEC.loader is not None
PACK_LOADER_MODULE = importlib.util.module_from_spec(PACK_LOADER_SPEC)
PACK_LOADER_SPEC.loader.exec_module(PACK_LOADER_MODULE)


class PackListing(TypedDict):
    name: str
    description: str
    entry_modules: list[str]
    loaded: bool
    load_time_ms: float


class ImportStatePayload(TypedDict):
    stats: dict[str, float]
    vision_loaded: bool
    music_loaded: bool


class LoaderProtocol(Protocol):
    def list_packs(self) -> list[PackListing]: ...

    def get_load_stats(self) -> dict[str, float]: ...

    def load_pack(self, pack_name: str) -> bool: ...

    def is_pack_module(self, module_name: str) -> bool: ...


class PackLoaderProtocol(Protocol):
    def __call__(self, manifest_path: Path | None = None) -> LoaderProtocol: ...


class GetLoaderProtocol(Protocol):
    def __call__(self) -> LoaderProtocol: ...


class PackLoaderModuleProtocol(Protocol):
    PackLoader: PackLoaderProtocol
    get_loader: GetLoaderProtocol


pack_loader_module = cast(
    PackLoaderModuleProtocol, cast(ModuleType, PACK_LOADER_MODULE)
)
PackLoader = pack_loader_module.PackLoader
get_loader = pack_loader_module.get_loader


def test_pack_loader_loads_manifest():
    loader = PackLoader()
    packs = loader.list_packs()
    assert len(packs) >= 3, "Should have at least 3 packs defined"


def test_pack_list_has_required_fields():
    loader = PackLoader()
    for pack in loader.list_packs():
        assert "name" in pack
        assert "description" in pack
        assert "entry_modules" in pack
        assert "loaded" in pack


def test_load_stats_empty_initially():
    loader = PackLoader()
    stats = loader.get_load_stats()
    assert isinstance(stats, dict)


def test_load_nonexistent_pack_returns_false():
    loader = PackLoader()
    result = loader.load_pack("nonexistent-pack-xyz")
    assert result is False


def test_is_pack_module_detects_pack():
    loader = PackLoader()
    packs = loader.list_packs()
    if packs:
        first_pack = packs[0]
        if first_pack["entry_modules"]:
            module_name = first_pack["entry_modules"][0]
            assert loader.is_pack_module(module_name) is True


def test_is_pack_module_excludes_core():
    loader = PackLoader()
    assert loader.is_pack_module("runtime.mutation_gate") is False
    assert loader.is_pack_module("runtime.proof_gate") is False


def test_get_loader_returns_singleton():
    l1 = get_loader()
    l2 = get_loader()
    assert l1 is l2


def test_core_import_not_loading_packs():
    command = [
        sys.executable,
        "-c",
        (
            "import importlib.util, json, pathlib, sys; "
            f"path = pathlib.Path({str(PACK_LOADER_PATH)!r}); "
            "spec = importlib.util.spec_from_file_location('isolated_pack_loader', path); "
            "assert spec is not None and spec.loader is not None; "
            "module = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(module); "
            "loader = module.PackLoader(); "
            "print(json.dumps({"
            "'stats': loader.get_load_stats(), "
            "'vision_loaded': any('vision_artifact' in m for m in sys.modules), "
            "'music_loaded': any('music_omr' in m for m in sys.modules)"
            "}))"
        ),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    payload = cast(ImportStatePayload, json.loads(result.stdout))
    assert payload["stats"] == {}
    assert not payload["vision_loaded"], (
        "Vision pack should not be loaded by core import"
    )
    assert not payload["music_loaded"], (
        "Music OMR pack should not be loaded by core import"
    )
