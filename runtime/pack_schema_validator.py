from __future__ import annotations

from pathlib import Path
from typing import TypedDict, cast

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


class ValidationResult(TypedDict):
    valid: bool
    errors: list[str]
    warnings: list[str]
    pack_name: str


_RECOMMENDED_FIELDS = ("rules", "prompts", "scaffold", "evidence")


def _is_string_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    for item in cast(list[object], value):
        if not isinstance(item, str):
            return False
    return True


def _load_pack(pack_path: Path) -> tuple[dict[str, object] | None, list[str]]:
    if not pack_path.exists():
        return None, [f"pack file not found: {pack_path}"]

    if _yaml is None:
        return None, ["PyYAML is unavailable"]

    try:
        loaded = cast(object, _yaml.safe_load(pack_path.read_text(encoding="utf-8")))
    except Exception as exc:
        return None, [f"failed to parse pack yaml: {exc}"]

    if not isinstance(loaded, dict):
        return None, ["pack yaml must be a mapping/object"]

    return cast(dict[str, object], loaded), []


def _record_missing_field(
    field: str,
    strict: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    message = f"missing recommended field: {field}"
    if strict:
        errors.append(message)
    else:
        warnings.append(message)


def validate_pack(pack_path: str | Path, strict: bool = False) -> ValidationResult:
    path = Path(pack_path)
    data, errors = _load_pack(path)
    warnings: list[str] = []
    pack_name = path.stem

    if data is None:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "pack_name": pack_name,
        }

    raw_name = data.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        pack_name = raw_name.strip()
    else:
        errors.append("missing required field: name")

    for field in _RECOMMENDED_FIELDS:
        if field not in data:
            _record_missing_field(field, strict, errors, warnings)

    rules = data.get("rules")
    if isinstance(rules, list):
        rules_list = cast(list[object], rules)
        rule_count = len(rules_list)
        if strict and rule_count != 9 and rule_count > 5:
            errors.append(
                f"rules list exceeds 5 entries for new packs: {rule_count} entries"
            )
    elif "rules" in data:
        errors.append("invalid field type: rules must be a list of strings")

    for field in ("prompts", "scaffold"):
        value = data.get(field)
        if field in data and not _is_string_list(value):
            errors.append(f"invalid field type: {field} must be a list of strings")

    evidence = data.get("evidence")
    if "evidence" in data and not isinstance(evidence, dict):
        errors.append("invalid field type: evidence must be a mapping/object")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "pack_name": pack_name,
    }
