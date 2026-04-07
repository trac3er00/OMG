from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict


class LoopDetectionResult(TypedDict):
    detected: bool
    type: str | None
    suggestion: str | None
    history_analyzed: int


_REPETITION_SUGGESTION = "Try reading the error output more carefully"
_OSCILLATION_SUGGESTION = "Take a different approach - the A/B cycle isn't converging"
_STAGNATION_SUGGESTION = "Try a different file or ask for clarification"


def detect_loop(call_history: Sequence[Mapping[str, object]]) -> LoopDetectionResult:
    history = [_normalize_call(call) for call in call_history]
    history_analyzed = len(history)
    if history_analyzed < 3:
        return _result(False, None, None, history_analyzed)

    repetition = _detect_repetition(history)
    if repetition["detected"]:
        return repetition

    oscillation = _detect_oscillation(history)
    if oscillation["detected"]:
        return oscillation

    stagnation = _detect_stagnation(history)
    if stagnation["detected"]:
        return stagnation

    return _result(False, None, None, history_analyzed)


def _detect_repetition(history: Sequence[dict[str, Any]]) -> LoopDetectionResult:
    if len(history) < 3:
        return _result(False, None, None, len(history))

    streak = 1
    previous_signature = _call_signature(history[0])
    for call in history[1:]:
        signature = _call_signature(call)
        if signature == previous_signature:
            streak += 1
            if streak >= 3:
                return _result(True, "repetition", _REPETITION_SUGGESTION, len(history))
        else:
            streak = 1
            previous_signature = signature

    return _result(False, None, None, len(history))


def _detect_oscillation(history: Sequence[dict[str, Any]]) -> LoopDetectionResult:
    if len(history) < 4:
        return _result(False, None, None, len(history))

    for window_size in (6, 4):
        if len(history) < window_size:
            continue
        window = history[-window_size:]
        first_signature = _call_signature(window[0])
        second_signature = _call_signature(window[1])
        if first_signature == second_signature:
            continue
        if all(
            _call_signature(call)
            == (first_signature if index % 2 == 0 else second_signature)
            for index, call in enumerate(window)
        ):
            return _result(True, "oscillation", _OSCILLATION_SUGGESTION, len(history))

    return _result(False, None, None, len(history))


def _detect_stagnation(history: Sequence[dict[str, Any]]) -> LoopDetectionResult:
    if len(history) < 5:
        return _result(False, None, None, len(history))

    for start in range(len(history) - 5, -1, -1):
        window = history[start:]
        if len(window) < 5:
            continue
        touched_paths = {_extract_path(call["args"]) for call in window}
        touched_paths.discard(None)
        if len(touched_paths) != 1:
            continue
        tools = [str(call["tool"]) for call in window]
        if len(set(tools)) != len(tools):
            continue
        return _result(True, "stagnation", _STAGNATION_SUGGESTION, len(history))

    return _result(False, None, None, len(history))


def _normalize_call(call: Mapping[str, object]) -> dict[str, Any]:
    tool = str(call.get("tool", "")).strip()
    raw_args = call.get("args", {})
    args = dict(raw_args) if isinstance(raw_args, Mapping) else {}
    return {"tool": tool, "args": args}


def _call_signature(call: Mapping[str, Any]) -> tuple[str, str]:
    return str(call.get("tool", "")), _serialize_args(call.get("args", {}))


def _serialize_args(args: object) -> str:
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(args), ensure_ascii=True)


def _extract_path(args: Mapping[str, Any]) -> str | None:
    for key in ("path", "file_path"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _result(
    detected: bool,
    detection_type: str | None,
    suggestion: str | None,
    history_analyzed: int,
) -> LoopDetectionResult:
    return {
        "detected": detected,
        "type": detection_type,
        "suggestion": suggestion,
        "history_analyzed": history_analyzed,
    }
