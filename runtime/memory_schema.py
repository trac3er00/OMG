from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CATEGORIES = (
    "decisions",
    "preferences",
    "failures",
    "open_loops",
    "team_context",
)


class MemoryTier(str, Enum):
    AUTO = "auto"
    MICRO = "micro"
    SHIP = "ship"


@dataclass
class TierConfig:
    promotion_threshold: int = 3
    demotion_ttl_seconds: int = 3600
    auto_max_items: int = 500
    micro_max_items: int = 10_000
    ship_max_items: int = 100_000


_SCHEMAS: dict[str, dict[str, type]] = {
    "decisions": {
        "decision": str,
        "rationale": str,
    },
    "preferences": {
        "preference": str,
        "value": str,
    },
    "failures": {
        "what": str,
        "why": str,
    },
    "open_loops": {
        "task": str,
        "status": str,
    },
    "team_context": {
        "member": str,
        "role": str,
    },
}

_OPTIONAL_FIELDS: dict[str, list[str]] = {
    "decisions": ["tags", "confidence", "source"],
    "preferences": ["scope", "notes"],
    "failures": ["resolution", "tags"],
    "open_loops": ["due", "priority"],
    "team_context": ["email", "timezone"],
}


class SchemaValidationError(ValueError):
    pass


def validate(category: str, data: dict[str, object]) -> None:
    if category not in CATEGORIES:
        raise SchemaValidationError(
            f"Unknown category '{category}'. Valid categories: {', '.join(CATEGORIES)}"
        )

    schema = _SCHEMAS[category]
    optional = set(_OPTIONAL_FIELDS.get(category, []))

    for field_name, field_type in schema.items():
        if field_name not in data:
            raise SchemaValidationError(
                f"Category '{category}' requires field '{field_name}' (type: "
                + f"{field_type.__name__}). Required fields: {list(schema.keys())}"
            )
        if not isinstance(data[field_name], field_type):
            raise SchemaValidationError(
                f"Field '{field_name}' must be {field_type.__name__}, got {type(data[field_name]).__name__}"
            )

    all_valid = set(schema.keys()) | optional | {"timestamp", "id", "category"}
    unknown = set(data.keys()) - all_valid
    if unknown:
        raise SchemaValidationError(
            f"Unknown fields for category '{category}': {', '.join(sorted(unknown))}. "
            + f"Valid fields: {', '.join(sorted(all_valid))}"
        )


def get_schema_description(category: str) -> str:
    if category not in CATEGORIES:
        return f"Unknown category: {category}"

    schema = _SCHEMAS[category]
    optional = _OPTIONAL_FIELDS.get(category, [])
    required = [f"{key} ({value.__name__})" for key, value in schema.items()]
    return (
        f"Category: {category}\n"
        f"Required fields: {', '.join(required)}\n"
        f"Optional fields: {', '.join(optional) or 'none'}"
    )
