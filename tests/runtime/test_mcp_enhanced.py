from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast


class ComputeScoreFn(Protocol):
    def __call__(self, evidence_list: list[dict[str, object]] | None) -> object: ...


class SetModeFn(Protocol):
    def __call__(self, mode: str) -> object: ...


class DetectLoopFn(Protocol):
    def __call__(self, call_history: list[dict[str, object]]) -> object: ...


class RunInstantFn(Protocol):
    def __call__(self, prompt: str, target_dir: str) -> object: ...


def _load_compute_score() -> ComputeScoreFn:
    return cast(ComputeScoreFn, import_module("runtime.proof_score").compute_score)


def _load_set_mode() -> SetModeFn:
    return cast(SetModeFn, import_module("runtime.model_toggle").set_mode)


def _load_detect_loop() -> DetectLoopFn:
    return cast(DetectLoopFn, import_module("runtime.loop_breaker").detect_loop)


def _load_run_instant() -> RunInstantFn:
    return cast(RunInstantFn, import_module("runtime.instant_mode").run_instant)


def test_proof_score_compute_score_is_importable() -> None:
    compute_score = _load_compute_score()

    assert callable(compute_score)


def test_model_toggle_set_mode_is_importable() -> None:
    set_mode = _load_set_mode()

    assert callable(set_mode)


def test_loop_breaker_detect_loop_is_importable() -> None:
    detect_loop = _load_detect_loop()

    assert callable(detect_loop)


def test_instant_mode_run_instant_is_importable() -> None:
    run_instant = _load_run_instant()

    assert callable(run_instant)


def test_mcp_enhanced_capabilities_import_together_without_conflict() -> None:
    compute_score = _load_compute_score()
    set_mode = _load_set_mode()
    detect_loop = _load_detect_loop()
    run_instant = _load_run_instant()

    assert callable(compute_score)
    assert callable(set_mode)
    assert callable(detect_loop)
    assert callable(run_instant)
