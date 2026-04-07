from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast


class ColdStartPayload(TypedDict):
    elapsed: float
    stats: dict[str, float | int]


class ListPacksPayload(TypedDict):
    elapsed: float
    count: int
    names: list[str]


class ModulesPayload(TypedDict):
    vision_modules: list[str]
    load_stats: dict[str, float]


class CoreManifestPayload(TypedDict):
    core_modules: list[str]
    loaded: dict[str, bool]


class StartupStatsPayload(TypedDict):
    startup_time_ms: float
    core_module_count: int
    pack_count: int


ROOT = Path(__file__).resolve().parents[2]


def _script(*parts: str) -> str:
    return " ".join(parts)


def _run_python(
    code: str, *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(cwd or ROOT),
    )


def test_pack_loader_cold_start_under_budget(
    tmp_project: Path,
    clean_env: None,
) -> None:
    del clean_env
    result = _run_python(
        _script(
            "import json, time;",
            "t=time.perf_counter();",
            "from runtime.pack_loader import PackLoader;",
            "loader=PackLoader();",
            "elapsed=time.perf_counter()-t;",
            "print(json.dumps({'elapsed': elapsed, 'stats': loader.get_startup_stats()}))",
        ),
        cwd=tmp_project,
    )
    payload = cast(ColdStartPayload, json.loads(result.stdout))
    assert payload["elapsed"] < 0.2
    assert payload["stats"]["startup_time_ms"] < 200.0


def test_list_packs_under_budget_and_discovers_all_manifest_packs(
    tmp_project: Path,
    clean_env: None,
) -> None:
    del clean_env
    result = _run_python(
        _script(
            "import json, time;",
            "from runtime.pack_loader import PackLoader;",
            "loader=PackLoader();",
            "t=time.perf_counter();",
            "packs=loader.list_packs();",
            "elapsed=time.perf_counter()-t;",
            "print(json.dumps({'elapsed': elapsed, 'count': len(packs), 'names': [p['name'] for p in packs]}))",
        ),
        cwd=tmp_project,
    )
    payload = cast(ListPacksPayload, json.loads(result.stdout))
    assert payload["elapsed"] < 0.5
    assert payload["count"] >= 6
    assert "vision" in payload["names"]
    assert "eval" in payload["names"]


def test_vision_modules_not_loaded_before_load_pack(
    tmp_project: Path,
    clean_env: None,
) -> None:
    del clean_env
    result = _run_python(
        _script(
            "import json, sys;",
            "from runtime.pack_loader import PackLoader;",
            "PackLoader();",
            "vision=[name for name in sys.modules if name.startswith('runtime.vision_')];",
            "print(json.dumps({'vision_modules': vision, 'load_stats': {}}))",
        ),
        cwd=tmp_project,
    )
    payload = cast(ModulesPayload, json.loads(result.stdout))
    assert payload["vision_modules"] == []


def test_vision_modules_loaded_after_load_pack(
    tmp_project: Path,
    clean_env: None,
) -> None:
    del clean_env
    result = _run_python(
        _script(
            "import json, sys;",
            "from runtime.pack_loader import PackLoader;",
            "loader=PackLoader();",
            "assert loader.load_pack('vision') is True;",
            "vision=sorted(name for name in sys.modules if name.startswith('runtime.vision_'));",
            "print(json.dumps({'vision_modules': vision, 'load_stats': loader.get_load_stats()}))",
        ),
        cwd=tmp_project,
    )
    payload = cast(ModulesPayload, json.loads(result.stdout))
    assert "runtime.vision_artifacts" in payload["vision_modules"]
    assert "runtime.vision_jobs" in payload["vision_modules"]
    assert payload["load_stats"]["vision"] >= 0.0


def test_core_modules_load_eagerly_with_explicit_manifest(
    tmp_project: Path,
    clean_env: None,
) -> None:
    del clean_env
    result = _run_python(
        _script(
            "import json, sys;",
            "from runtime.core_imports import CORE_MODULES;",
            "from runtime.pack_loader import PackLoader;",
            "PackLoader();",
            "loaded={name: ('runtime.' + name) in sys.modules for name in CORE_MODULES};",
            "print(json.dumps({'core_modules': CORE_MODULES, 'loaded': loaded}))",
        ),
        cwd=tmp_project,
    )
    payload = cast(CoreManifestPayload, json.loads(result.stdout))
    assert 0 < len(payload["core_modules"]) < 20
    assert payload["loaded"]["mutation_gate"] is True
    assert payload["loaded"]["proof_gate"] is True
    assert payload["loaded"]["claim_judge"] is True
    assert payload["loaded"]["memory_store"] is True


def test_get_startup_stats_reports_core_and_pack_counts(
    tmp_project: Path,
    clean_env: None,
) -> None:
    del clean_env
    result = _run_python(
        _script(
            "import json;",
            "from runtime.pack_loader import PackLoader;",
            "stats=PackLoader().get_startup_stats();",
            "print(json.dumps(stats))",
        ),
        cwd=tmp_project,
    )
    payload = cast(StartupStatsPayload, json.loads(result.stdout))
    assert payload["core_module_count"] > 0
    assert payload["pack_count"] >= 6
    assert payload["startup_time_ms"] >= 0.0
