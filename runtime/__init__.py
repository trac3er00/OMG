"""Runtime package for OMG."""

from __future__ import annotations

import importlib
import time
from typing import cast

build_compat_gap_report: object
build_omg_gap_report: object
dispatch_compat_skill: object
dispatch_omg_skill: object
get_compat_skill_contract: object
get_omg_skill_contract: object
list_compat_skill_contracts: object
list_compat_skills: object
list_omg_skill_contracts: object
list_omg_skills: object
ecosystem_status: object
list_ecosystem_repos: object
resolve_ecosystem_selection: object
sync_ecosystem_repos: object
run_vision_job: object
write_vision_artifacts: object


_STARTUP_TIMER = time.perf_counter()

_LAZY_EXPORTS = {
    "build_compat_gap_report": ("runtime.compat", "build_compat_gap_report"),
    "build_omg_gap_report": ("runtime.compat", "build_omg_gap_report"),
    "dispatch_compat_skill": ("runtime.compat", "dispatch_compat_skill"),
    "dispatch_omg_skill": ("runtime.compat", "dispatch_omg_skill"),
    "get_compat_skill_contract": ("runtime.compat", "get_compat_skill_contract"),
    "get_omg_skill_contract": ("runtime.compat", "get_omg_skill_contract"),
    "list_compat_skill_contracts": ("runtime.compat", "list_compat_skill_contracts"),
    "list_compat_skills": ("runtime.compat", "list_compat_skills"),
    "list_omg_skill_contracts": ("runtime.compat", "list_omg_skill_contracts"),
    "list_omg_skills": ("runtime.compat", "list_omg_skills"),
    "ecosystem_status": ("runtime.ecosystem", "ecosystem_status"),
    "list_ecosystem_repos": ("runtime.ecosystem", "list_ecosystem_repos"),
    "resolve_ecosystem_selection": ("runtime.ecosystem", "resolve_ecosystem_selection"),
    "sync_ecosystem_repos": ("runtime.ecosystem", "sync_ecosystem_repos"),
    "run_vision_job": ("runtime.vision_jobs", "run_vision_job"),
    "write_vision_artifacts": ("runtime.vision_artifacts", "write_vision_artifacts"),
}


def __getattr__(name: str) -> object:
    export = _LAZY_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    value = cast(object, getattr(importlib.import_module(module_name), attr_name))
    globals()[name] = value
    return value


RUNTIME_STARTUP_STATS = {
    "module": __name__,
    "startup_time_ms": 0.0,
    "lazy_exports": tuple(sorted(_LAZY_EXPORTS)),
}

__all__ = [
    "build_compat_gap_report",
    "build_omg_gap_report",
    "dispatch_compat_skill",
    "dispatch_omg_skill",
    "get_compat_skill_contract",
    "get_omg_skill_contract",
    "list_compat_skill_contracts",
    "list_compat_skills",
    "list_omg_skill_contracts",
    "list_omg_skills",
    "ecosystem_status",
    "list_ecosystem_repos",
    "resolve_ecosystem_selection",
    "sync_ecosystem_repos",
    "run_vision_job",
    "write_vision_artifacts",
]

RUNTIME_STARTUP_STATS["startup_time_ms"] = (time.perf_counter() - _STARTUP_TIMER) * 1000
