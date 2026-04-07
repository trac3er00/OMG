from __future__ import annotations

import importlib
from types import ModuleType


CORE_MODULES = [
    "mutation_gate",
    "proof_gate",
    "claim_judge",
    "memory_store",
]


def eager_import_core_modules() -> dict[str, ModuleType]:
    loaded: dict[str, ModuleType] = {}
    for module_name in CORE_MODULES:
        qualified_name = f"runtime.{module_name}"
        loaded[module_name] = importlib.import_module(qualified_name)
    return loaded
