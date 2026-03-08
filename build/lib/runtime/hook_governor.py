"""Hook-order validation using the canonical hook-governor bundle."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Literal, TypedDict, cast

try:
    import yaml
except Exception:  # pragma: no cover - json fallback path
    yaml = None


DEFAULT_BUNDLE_PATH = Path("registry") / "bundles" / "hook-governor.yaml"
SECURITY_REQUIRED_BY_EVENT: dict[str, tuple[str, ...]] = {
    "PreToolUse": ("firewall", "secret-guard"),
}


class ValidationResult(TypedDict):
    status: Literal["ok", "blocked"]
    blockers: list[str]


def _resolve_project_dir(project_dir: str | None) -> Path:
    if project_dir:
        return Path(project_dir)
    env_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_project_dir:
        return Path(env_project_dir)
    return Path.cwd()


def _extract_hook_name(command: str) -> str:
    matches = cast(list[str], re.findall(r"([A-Za-z0-9_.-]+\.py)", command))
    if matches:
        return Path(matches[-1]).stem
    tokens = command.strip().split()
    if not tokens:
        return ""
    return Path(tokens[-1].strip("\"'")).stem


def _load_compiled_hooks(
    project_dir: str | None = None,
    bundle_path: str | None = None,
) -> tuple[dict[str, list[str]], str | None]:
    root = _resolve_project_dir(project_dir)
    candidate = Path(bundle_path) if bundle_path else (root / DEFAULT_BUNDLE_PATH)
    try:
        raw = candidate.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, f"canonical hook bundle missing: {candidate}"
    except Exception as exc:
        return {}, f"failed reading canonical hook bundle: {exc}"

    try:
        parsed_obj: object
        if yaml is not None:
            parsed_obj = cast(object, yaml.safe_load(raw))
            if parsed_obj is None:
                parsed_obj = {}
        else:
            parsed_obj = cast(object, json.loads(raw))
    except Exception as exc:
        return {}, f"failed parsing canonical hook bundle: {exc}"

    if not isinstance(parsed_obj, dict):
        return {}, "invalid canonical hook bundle payload"

    payload = cast(dict[object, object], parsed_obj)
    compiled_hooks_obj = payload.get("compiled_hooks")
    if not isinstance(compiled_hooks_obj, dict):
        return {}, "compiled_hooks missing from canonical hook bundle"

    compiled_hooks = cast(dict[object, object], compiled_hooks_obj)
    canonical: dict[str, list[str]] = {}
    for event_key, hooks_obj in compiled_hooks.items():
        if not isinstance(event_key, str) or not isinstance(hooks_obj, list):
            continue
        names: list[str] = []
        for hook_entry in cast(list[object], hooks_obj):
            if not isinstance(hook_entry, dict):
                continue
            hook_map = cast(dict[object, object], hook_entry)
            command_obj = hook_map.get("command")
            if not isinstance(command_obj, str):
                continue
            hook_name = _extract_hook_name(command_obj)
            if hook_name:
                names.append(hook_name)
        canonical[event_key] = names
    return canonical, None


def get_canonical_order(
    event: str,
    *,
    project_dir: str | None = None,
    bundle_path: str | None = None,
) -> list[str]:
    compiled_hooks, _ = _load_compiled_hooks(project_dir=project_dir, bundle_path=bundle_path)
    return list(compiled_hooks.get(event, ()))


def validate_order(
    event: str,
    hooks_list: list[str],
    *,
    project_dir: str | None = None,
    bundle_path: str | None = None,
) -> ValidationResult:
    compiled_hooks, load_error = _load_compiled_hooks(project_dir=project_dir, bundle_path=bundle_path)
    if load_error:
        return {"status": "blocked", "blockers": [load_error]}

    canonical = compiled_hooks.get(event, [])
    if not canonical:
        return {"status": "blocked", "blockers": [f"no canonical hook order for event {event}"]}

    blockers: list[str] = []
    expected_positions = {name: idx for idx, name in enumerate(canonical)}

    for required in SECURITY_REQUIRED_BY_EVENT.get(event, ()):
        if required not in hooks_list:
            blockers.append(f"missing required security hook: {required}")

    filtered_hooks = [hook for hook in hooks_list if hook in expected_positions]
    for left, right in zip(filtered_hooks, filtered_hooks[1:]):
        if expected_positions[left] > expected_positions[right]:
            blockers.append(
                f"hook order violation for {event}: {left} must run after {right} in canonical order"
            )

    status: Literal["ok", "blocked"] = "blocked" if blockers else "ok"
    return {"status": status, "blockers": blockers}
