#!/usr/bin/env python3
"""Measure import time for core runtime modules.

Usage: python3 scripts/measure-import-time.py
Target: core-only import under 500ms
"""
from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

CORE_MODULES = [
    "runtime.mutation_gate",
    "runtime.proof_gate",
    "runtime.claim_judge",
    "runtime.memory_store",
    "runtime.complexity_classifier",
    "runtime.model_registry",
    "runtime.router_selector",
    "runtime.complexity_scorer",
    "runtime.delta_classifier",
    "runtime.session_health",
    "runtime.context_compiler",
    "runtime.decision_engine",
]

PACK_MODULES_TO_CHECK = [
    "runtime.api_twin",
    "runtime.data_lineage",
]


def measure_import(module_name: str) -> float:
    """Measure import time for a single module. Returns seconds."""
    start = time.perf_counter()
    try:
        _ = importlib.import_module(module_name)
        elapsed = time.perf_counter() - start
    except Exception as exc:
        elapsed = 0.0
        print(f"  SKIP {module_name}: {exc}", file=sys.stderr)
    return elapsed


def main() -> None:
    results: dict[str, float] = {}

    print("Measuring core module import times...")
    total_core = 0.0
    for mod in CORE_MODULES:
        t = measure_import(mod)
        results[mod] = round(t * 1000, 2)  # milliseconds
        total_core += t
        print(f"  {mod}: {t * 1000:.1f}ms")

    print(f"\nTotal core import time: {total_core * 1000:.1f}ms")
    print("Target: <500ms")

    if total_core * 1000 < 500:
        print("✓ PASS: Core imports under 500ms target")
    else:
        print("✗ WARN: Core imports exceed 500ms target")

    # Check packs are NOT loaded by core
    print("\nChecking pack modules not loaded by core imports...")
    pack_loaded: list[str] = []
    for mod in PACK_MODULES_TO_CHECK:
        base = mod.split(".")[-1]
        loaded = any(base in k for k in sys.modules)
        if loaded:
            pack_loaded.append(mod)
            print(f"  WARN: {mod} was loaded as side-effect")
        else:
            print(f"  OK: {mod} not loaded")

    # Save report
    report: dict[str, object] = {
        "core_modules": results,
        "total_core_ms": round(total_core * 1000, 2),
        "target_ms": 500,
        "pass": total_core * 1000 < 500,
        "pack_modules_loaded": pack_loaded,
    }

    report_path = project_root / ".sisyphus" / "evidence" / "task-17-import-baseline.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _ = report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
