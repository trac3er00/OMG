#!/usr/bin/env python3
"""Kimi host hook adapter — bridges Kimi events to OMG hook system."""

from __future__ import annotations

import json
import sys
from typing import cast


def _json_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    source = cast(dict[object, object], value)
    normalized: dict[str, object] = {}
    for raw_key, raw_item in source.items():
        normalized[str(raw_key)] = raw_item
    return normalized


def _extract_command(payload: dict[str, object]) -> str:
    input_payload = _json_object(payload.get("input"))
    if input_payload is not None:
        command = input_payload.get("command")
        if isinstance(command, str):
            return command

    tool_input = _json_object(payload.get("tool_input"))
    if tool_input is not None:
        command = tool_input.get("command")
        if isinstance(command, str):
            return command

    return ""


def _contains_dangerous_pattern(command: str) -> bool:
    normalized = " ".join(command.split()).lower()
    blocked_patterns = ("rm -rf", "chmod 777", "curl | bash")
    return any(pattern in normalized for pattern in blocked_patterns)


def handle_pre_tool_use(payload: dict[str, object], tool: str) -> dict[str, str]:
    dangerous_tools = {"Bash", "Execute", "Shell"}
    if tool in dangerous_tools:
        command = _extract_command(payload)
        if _contains_dangerous_pattern(command):
            return {
                "decision": "deny",
                "reason": "dangerous command blocked by kimi-adapter",
            }
    return {"decision": "allow"}


def handle_post_tool_use(_payload: dict[str, object], _tool: str) -> dict[str, str]:
    return {"decision": "allow"}


def main() -> None:
    try:
        raw_payload = cast(object, json.loads(sys.stdin.read()))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow", "error": "invalid JSON"}))
        return

    payload = _json_object(raw_payload)
    if payload is None:
        print(json.dumps({"decision": "allow"}))
        return

    event_obj = payload.get("event")
    event = event_obj if isinstance(event_obj, str) else ""
    tool_obj = payload.get("tool")
    if isinstance(tool_obj, str):
        tool = tool_obj
    else:
        tool_name_obj = payload.get("tool_name")
        tool = tool_name_obj if isinstance(tool_name_obj, str) else ""
    host_obj = payload.get("host")
    host = host_obj if isinstance(host_obj, str) else ""

    if host and host != "kimi":
        print(json.dumps({"decision": "allow"}))
        return

    if event == "PreToolUse":
        decision = handle_pre_tool_use(payload, tool)
    elif event == "PostToolUse":
        decision = handle_post_tool_use(payload, tool)
    else:
        decision = {"decision": "allow"}

    print(json.dumps(decision))


if __name__ == "__main__":
    main()
